"""Trace both GPU Runs, replay the source audit, and time raw-to-finish execution."""
import argparse
from collections import Counter
import json
from pathlib import Path
from statistics import median
from time import perf_counter_ns

import numpy as np
import torch

from network import certified_read
from experiment import Coordinator, cpu, dataset, device, digest, load_producer
from experiment import produce, static, study, upload

from audit_locality import count, change_requests, PANELS, LANES


def execute(model,producer,inputs,table,ports,lane):
    make,token=produce(producer,inputs,table)
    controls=(inputs[2],*inputs[4:])
    if lane=='certified':
        second=certified_read(token,controls,ports)
        return make,second,torch.zeros_like(second['active'],dtype=torch.bool),None,token
    state=model.prepare(token,controls,ports,'global' if lane=='global' else 'local')
    delivery=lane if lane in ('drop','stale','mute') else 'current'
    if lane=='resend':
        old,_,waiting,_=model.finish(token,controls,ports,state,'stale')
        current,_,more,_=model.finish(token,controls,ports,state)
        # Only pending request slots may be replaced on retry.
        final={k:torch.where(waiting if k=='active' else waiting[...,None],current[k],v) for k,v in old.items()}
        return make,final,waiting & more,state,token
    final,_,waiting,_=model.finish(token,controls,ports,state,delivery)
    return make,final,waiting,state,token


@torch.inference_mode()
def evaluate(root,previous):
    dev=device();_,train,templates,schema=study()
    secondary=[t for t in train if t['id'] in ('rule-266','rule-267','rule-580')]
    assert len(secondary)==3
    reports={};timing={};hashes={};isolation={};weights={}
    archive=root/'traces';archive.mkdir(exist_ok=True)
    for seed in (1703,1709):
        producer=load_producer(schema,seed,previous,dev);models={};info={}
        for scope in ('global','local'):
            path=root/f'{scope}-{seed}.pt'
            info[scope]=json.loads(path.with_suffix('.json').read_text())
            assert info[scope]['weight']==digest(path)
            model=Coordinator().to(dev)
            model.load_state_dict(torch.load(path,map_location='cpu',weights_only=True))
            models[scope]=model.eval()
        assert all(info['global'][key]==info['local'][key] for key in ('params','initial','batches'))
        weights[seed]=info
        for template in [*templates,*secondary]:
            name=template['id'];ports=static(template,dev)
            base=dataset('test',template)
            table=producer.encoder.encode_bank(schema.bank(template,'pairwise',dev))
            original_file=previous/'traces'/f'{name}-pairwise-{seed}.npz'
            held=template['split']=='heldout'
            if held:
                hashes[original_file.name]=digest(original_file)
                with np.load(original_file,allow_pickle=False) as original:
                    source={k:original['0_'+k] for k in ('active','pointers','rows')}
            for panel in (PANELS if held else ('seen-secondary',)):
                d=base if panel=='seen-secondary' else change_requests(base,panel)
                x=upload(d,slice(None),dev);current=None;stale=None;arr={}
                for lane in LANES:
                    m=models['global' if lane=='global' else 'local']
                    f,s,waiting,state,token=execute(m,producer,x,table,ports,lane)
                    first,second=cpu(f),cpu(s);pending=waiting.cpu().numpy()
                    if held:
                        for k in first:np.testing.assert_array_equal(first[k],source[k])
                    if lane=='global':
                        for k in first:arr['first_'+k]=first[k]
                    else:
                        for k in first:np.testing.assert_array_equal(first[k],arr['first_'+k])
                    if lane in ('global','local') and panel=='original':
                        # Perturb only the remote producer latent, leaving source rows intact.
                        poisoned=token.clone()
                        poisoned[...,:32]+=7*(token[...,50:51]==1).float()
                        changed=m.prepare(poisoned,(x[2],*x[4:]),ports,lane)
                        equal=(state[:,0]==changed[:,0]).all(-1)
                        isolation[f'{seed}/{name}/{lane}']=int(equal.sum().item())
                        if lane=='local':assert equal.all().item()
                    if lane=='local':current=second
                    if lane=='mute':
                        local=d['requests'][...,0]==d['requests'][...,2]
                        for k in second:np.testing.assert_array_equal(second[k][local],current[k][local])
                    if lane=='stale':stale=arr['drop_active']
                    if lane=='resend':
                        for k in current:np.testing.assert_array_equal(current[k],second[k])
                    cross=d['requests'][...,0]!=d['requests'][...,2]
                    if lane in ('drop','stale'):
                        np.testing.assert_array_equal(pending,cross)
                        for k in second:np.testing.assert_array_equal(second[k][~cross],current[k][~cross])
                        if lane=='stale':np.testing.assert_array_equal(stale,second['active'])
                    scores=count(d,first,second,pending)
                    for group,score in scores.items():
                        key=f'{seed}/{panel}/{lane}/{group}'
                        reports.setdefault(key,Counter()).update(score)
                    for k,v in second.items():arr[lane+'_'+k]=v
                    arr[lane+'_pending']=pending
                path=archive/f'{seed}-{name}-{panel}.npz'
                np.savez_compressed(path,**arr)
                hashes[path.name]=digest(path)
                if panel=='original':
                    # Same graphs per lane, one raw graph per call. Compare every timed output.
                    indices=np.random.default_rng(703).permutation(len(d['a']))[:32]
                    for lane in LANES:
                        m=models['global' if lane=='global' else 'local']
                        for i in indices[:3]:
                            execute(m,producer,upload(d,slice(i,i+1),dev),table,ports,lane)
                            torch.mps.synchronize()
                    for j,i in enumerate(indices):
                        for lane in LANES[j%len(LANES):]+LANES[:j%len(LANES)]:
                            m=models['global' if lane=='global' else 'local'];start=perf_counter_ns()
                            f,s,w,_,_=execute(m,producer,upload(d,slice(i,i+1),dev),table,ports,lane)
                            torch.mps.synchronize()
                            timing.setdefault(f'{seed}/{lane}',[]).append((perf_counter_ns()-start)/1e6)
                            for k,v in cpu(s).items():np.testing.assert_array_equal(v[0],arr[lane+'_'+k][i])
                print(seed,name,panel,flush=True)
    return dict(panels=reports,elapsed_ms=timing,median_ms={k:median(v) for k,v in timing.items()},
                unperturbed_owner_bitwise_equal=isolation,inputs_outputs_sha256=hashes,weights=weights)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('root',type=Path);p.add_argument('producers',type=Path)
    args=p.parse_args()
    (args.root/'results.json').write_text(json.dumps(evaluate(args.root,args.producers),indent=1)+'\n')

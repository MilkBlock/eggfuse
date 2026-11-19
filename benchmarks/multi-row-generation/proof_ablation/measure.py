"""Measure both verified GPU pipelines with the same frozen neural proposals."""
import argparse
import json
from pathlib import Path
from statistics import median
import sys
from time import perf_counter_ns

import numpy as np
import torch
from torch.nn import functional as F

from bake import plans
from device_proof import compiled,records,issue,verify,publish
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'locality_ablation'))
from experiment import dataset,device,load_producer,study,upload
from network import read_parent, project


def proposals(model,x,table,p,source):
    stages,token,_=model(*x,table)
    if source=='all_requests':
        # Coverage diagnostic: propose every visible Request, irrespective of truth.
        req=x[2];picked,ptr,live=read_parent(token,req)
        s=project(picked,ptr,req,live,torch.ones_like(live))
        padded={k:F.pad(v,(0,4) if k=='active' else (0,0,0,4)) for k,v in s.items()}
        stages=(stages[0],padded)
    return records(x,stages,token,p)


def run(data,p,macro):
    packet=issue(data,p,macro)
    verdict=verify(data,p,*packet,macro)
    return packet,verdict,publish(data,verdict)


def host(v):return v.detach().cpu().numpy()


def challenges(data,p,packet,verdict,macro):
    wire,slices=map(host,packet)
    valid=host(verdict)[...,0].astype(bool)
    g,j=np.where(valid);offset=slices[g,j,0]
    parents=host(data[2]);requests=host(data[4]);dev=data[0].device
    out={}
    for fault in ('stale_epoch','unknown_template','missing_parent','wrong_live_parent','bad_proof','wrong_field','wrong_scope','truncated'):
        changed=wire.copy();lens=slices.copy();claims=host(data[3]).copy();ix=np.ones(len(g),bool)
        if fault=='stale_epoch':changed[g,offset+1]-=1
        elif fault=='unknown_template':changed[g,offset]=-1
        elif fault=='missing_parent':changed[g,offset+3]=-1;claims[g,j,1]=-1
        elif fault=='wrong_scope':changed[g,offset+2]+=1
        elif fault=='bad_proof':changed[g,offset+6]=2**30
        elif fault=='truncated':lens[g,j,1]-=1
        elif fault=='wrong_field':claims[g,j,5]+=1
        else:
            req=claims[g,j,2]
            other=(parents[g,:,0]!=0)&(parents[g,:,3:5]!=requests[g,req,2:4][:,None,:]).any(-1)
            ix=other.any(-1);alt=other.argmax(-1)[ix]
            changed[g[ix],offset[ix]+3]=alt;claims[g[ix],j[ix],1]=alt
        modified=(*data[:3],torch.as_tensor(claims,device=dev),*data[4:])
        decisions=verify(modified,p,torch.as_tensor(changed,device=dev),torch.as_tensor(lens,device=dev),macro)
        out[fault]=[int(ix.sum()),int(host(decisions)[g[ix],j[ix],0].sum())]
    return out


@torch.inference_mode()
def main(root,old):
    dev=device();all_t,_,_,schema=study();initial=plans()
    dest=root/'traces';dest.mkdir(parents=True,exist_ok=True)
    fault_stats={};times={};offline={};fees={};tags=set()
    for t in all_t:
        key=t['id'];held=t['split']=='heldout'
        if not held and key not in ('rule-266','rule-267','rule-580'):continue
        start=perf_counter_ns();p=compiled(t,initial[key],dev);torch.mps.synchronize()
        offline[key]=(perf_counter_ns()-start)/1e6
        tag=int(p['cfg'][0].item());assert tag not in tags;tags.add(tag)
        fees[key]={k:v.numel()*v.element_size() for k,v in p.items() if isinstance(v,torch.Tensor)}
        d=dataset('test',t);x=upload(d,slice(None),dev)
        for seed in (1703,1709):
            model=load_producer(schema,seed,old,dev)
            table=model.encoder.encode_bank(schema.bank(t,'pairwise',dev))
            for source in ('neural','all_requests'):
                data=proposals(model,x,table,p,source)
                saved={k:host(v) for k,v in zip(('a','b','parents','claims','requests','ctx'),data)}
                for mode in ('primitive','macro'):
                    macro=mode=='macro';packet,v,rows=run(data,p,macro)
                    saved.update({mode+'_'+k:host(w) for k,w in zip(('wire','ranges','verdict','rows'),(*packet,v,rows))})
                    faults=challenges(data,p,packet,v,macro)
                    fault_stats[f'{key}/{seed}/{source}/{mode}']=faults
                    if any(nbad for _,nbad in faults.values()):raise ValueError(faults)
                np.testing.assert_array_equal(saved['primitive_rows'],saved['macro_rows'])
                np.testing.assert_array_equal(saved['primitive_verdict'][...,0],saved['macro_verdict'][...,0])
                np.savez_compressed(dest/f'{key}-{seed}-{source}.npz',**saved)
                if source!='neural':continue
                ids=np.random.default_rng(1717).permutation(len(x[0]))[:16]
                for j,i in enumerate([*ids[:3],*ids]):
                    frozen=tuple(v[i:i+1] for v in data)
                    for mode in (('primitive','macro') if j%2 else ('macro','primitive')):
                        macro=mode=='macro';pre=issue(frozen,p,macro)
                        torch.mps.synchronize()
                        begin=perf_counter_ns()
                        verdict=verify(frozen,p,*pre,macro)
                        torch.mps.synchronize()
                        check_ms=(perf_counter_ns()-begin)/1e6
                        begin=perf_counter_ns()
                        single=proposals(model,upload(d,slice(i,i+1),dev),table,p,'neural')
                        _,_,rows=run(single,p,macro);torch.mps.synchronize()
                        whole_ms=(perf_counter_ns()-begin)/1e6
                        np.testing.assert_array_equal(host(rows)[0],saved[mode+'_rows'][i])
                        np.testing.assert_array_equal(host(verdict)[0],saved[mode+'_verdict'][i])
                        if j>=3:
                            for scope,ms in [('verify',check_ms),('whole',whole_ms)]:
                                name=f"{'heldout' if held else 'secondary'}/{seed}/{mode}/{scope}"
                                times.setdefault(name,[]).append(ms)
        print(key,flush=True)
    result=dict(faults=fault_stats,samples_ms=times,median_ms={k:median(v) for k,v in times.items()},
                cold_compile_upload_ms=offline,device_bytes=fees)
    (root/'measure.json').write_text(json.dumps(result)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('root',type=Path);p.add_argument('producers',type=Path)
    args=p.parse_args();main(args.root,args.producers)

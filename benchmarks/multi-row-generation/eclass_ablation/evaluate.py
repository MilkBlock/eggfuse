"""Eval actual two-stage neural generation and compare four instance-scoped graph views."""
import argparse
import itertools
import json
from pathlib import Path
import statistics
import time
import numpy as np
import torch

from model import AliasSystem, INPUTS
from fit import study, device, transfer, digest, MANIFEST, SEEDS
from encoder import ARMS
from data import dataset, audit, STATES


def subset(d,ix):
    return {k:(v[ix] if isinstance(v,np.ndarray) else v) for k,v in d.items()}


def host(out):
    stages,token,relation=out
    return (tuple({k:s[k].detach().cpu().numpy() for k in ('active','pointers','rows')} for s in stages),
            token.detach().cpu().numpy(),relation.detach().cpu().numpy())


def combine(chunks):
    stages=tuple({k:np.concatenate([s[i][k] for s,_,_ in chunks]) for k in ('active','pointers','rows')} for i in range(2))
    return stages,np.concatenate([t for _,t,_ in chunks]),np.concatenate([r for _,_,r in chunks])


def run_bulk(m,d,table,dev):
    chunks=[]
    for lo in range(0,len(d['a']),64):
        x=m(*transfer(d,slice(lo,lo+64),dev),table)
        torch.mps.synchronize();chunks.append(host(x))
    return combine(chunks)


def audit_trace(d,stages,token,rel):
    assert np.isfinite(token).all() and np.isfinite(rel).all()
    one=stages[0]
    np.testing.assert_array_equal(token[...,50:55],one['rows'])
    g=np.arange(len(token))[:,None]
    np.testing.assert_array_equal(token[...,-1],d['a_port'][g,one['pointers'][...,0]])
    r=audit(d,*stages)
    truth=np.array(r['request_legal'],dtype=int)
    np.testing.assert_array_equal(truth,d['request_legal'])
    return r,truth,rel.argmax(-1)


def group_stats(d,records,truth,pred,ix):
    rows=[records[i] for i in ix]
    num=lambda k:sum(int(v[k]) for v in rows)
    stage={k:num(k) for k in rows[0]}
    stage.update(graphs=len(ix),nonempty_complete=sum(v['nonempty'] and v['complete'] for v in rows),
                 complete_when_ready=sum(v['complete'] and v['nonempty'] and v['parent_ready'] for v in rows))
    y=truth[ix];p=pred[ix];req=d['requests'][ix]
    diff=(req[...,:2]!=req[...,2:4]).any(-1)
    for desc,mask in [('all',np.ones_like(y,bool)),('different_origins',diff),
                      ('cross_owner',req[...,0]!=req[...,2]),('local_probe',d['probe_kind'][ix]==1)]:
        stage['relation_'+desc]=dict(tests=int(mask.sum()),correct=int(((y==p)&mask).sum()),
              false_positive=int(((p==1)&(y==0)&mask).sum()),false_negative=int(((p==0)&(y==1)&mask).sum()),
              positive=int(((y==1)&mask).sum()))
    return stage


def diagnostics(d,stages,token,rel):
    report,truth,pred=audit_trace(d,stages,token,rel);state=d['state'];records=report['run2']['per_graph']
    # All eight variations of one source group have identical producer inputs.
    for name,v in stages[0].items():
        reshaped=v.reshape(-1,8,*v.shape[1:])
        np.testing.assert_array_equal(reshaped,np.broadcast_to(reshaped[:,:1],reshaped.shape))
    raw=token.reshape(-1,8,*token.shape[1:]);np.testing.assert_array_equal(raw,np.broadcast_to(raw[:,:1],raw.shape))
    masks={'all':np.ones(len(state),bool),'blind':d['blind']==1,'targeted':d['blind']==0}
    masks.update({name:state==i for i,name in enumerate(STATES)})
    masks.update({'blind_'+name:(d['blind']==1)&(state==i) for i,name in enumerate(STATES)})
    # Score only requests whose true answer changes between pre and post,
    # including both members of each pair so a constant predictor cannot pass.
    shape=(-1,4,2,4)
    y=truth.reshape(shape);p=pred.reshape(shape)
    change=y[:,0]!=y[:,1]
    switches=dict(changed=int(change.sum()),both_correct=int((change&(y[:,0]==p[:,0])&(y[:,1]==p[:,1])).sum()))
    flags={k:group_stats(d,records,truth,pred,np.flatnonzero(v)) for k,v in masks.items()}
    return dict(groups=flags,first_complete=report['run1']['complete_graphs'],complete=[int(v['complete']) for v in records],switches=switches)


def timings(d,models,banks,table,schema,t,dev):
    # Sample four complete counterfactual groups => balanced pre/post/nonmerge/external.
    groups=np.random.default_rng(6489).choice(len(d['a'])//8,4,replace=False)
    ids=np.concatenate([np.arange(i*8,i*8+8) for i in groups]);names=list(models);results={};warm_outputs={}
    for kind in ('cached','cold'):
        def call(name,i):
            m=models[name];x=transfer(d,slice(i,i+1),dev)
            cond=table[name] if kind=='cached' else m.encoder.encode_bank(schema.bank(t,name.split('-')[0],dev))
            return m(*x,cond)
        for name in names:
            for i in ids[:3]:call(name,i);torch.mps.synchronize()
        times={name:[] for name in names};kept={name:[] for name in names}
        for z,i in enumerate(ids):
            off=z%len(names)
            for name in names[off:]+names[:off]:
                start=time.perf_counter_ns();out=call(name,i);torch.mps.synchronize()
                times[name].append((time.perf_counter_ns()-start)/1e6);kept[name].append(out)
        measured={}
        for name in names:
            st,tok,rel=combine([host(o) for o in kept[name]])
            checked,_,_=audit_trace(subset(d,ids),st,tok,rel)
            if kind=='cached':warm_outputs[name]=st
            else:
                for first,second in zip(warm_outputs[name],st):
                    for k in first:np.testing.assert_array_equal(first[k],second[k])
            wins=checked['run2']['nonempty_complete_graphs']
            measured[name]=dict(samples_ms=times[name],median_ms=statistics.median(times[name]),success=wins,
                                valid_nonempty_per_second=1000*wins/sum(times[name]))
        results[kind]=measured
    return dict(indices=ids.tolist(),**results)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);args=parser.parse_args()
    templates,_,_,schema=study();models={};fits={};dev=device();seen={}
    for arm,seed in itertools.product(ARMS,SEEDS):
        name=f'{arm}-{seed}';folder=args.root/name;fit=json.loads((folder/'fit.json').read_text())
        assert fit['weight_sha256']==digest(folder/'final.pt') and fit['corpus_sha256']==digest(MANIFEST)
        common=(fit['initial_sha256'],fit['data_order_sha256'],fit['train_input_sha256'],fit['num_parameters'])
        if seed in seen:assert seen[seed]==common
        seen[seed]=common
        m=AliasSystem(schema,seed);m.load_state_dict(torch.load(folder/'final.pt',map_location='cpu',weights_only=True))
        models[name]=m.to(dev).eval();fits[name]=fit
    reports={};timed={};matched={};sizes={};folder=args.root/'traces';folder.mkdir(exist_ok=True)
    with torch.inference_mode():
        for t in templates:
            tid=t['id'];d=dataset('test',t)
            banks={n:schema.bank(t,n.split('-')[0],dev) for n in models}
            tables={n:models[n].encoder.frozen_bank(b) for n,b in banks.items()}
            sizes[tid]={n:[v.stats for v in b.views] for n,b in banks.items() if n.endswith('1703')}
            reports[tid]={}
            for n,m in models.items():
                st,tok,rel=run_bulk(m,d,tables[n],dev)
                reports[tid][n]=diagnostics(d,st,tok,rel)
                if t['split']=='heldout':
                    np.savez_compressed(folder/f'{tid}-{n}.npz',token=tok,rel=rel,**{f'{i}_{k}':v for i,s in enumerate(st) for k,v in s.items()})
            if t['split']!='heldout':continue
            timed[tid]=timings(d,models,banks,tables,schema,t,dev)
            matched[tid]={}
            for seed in SEEDS:
                name=f'pairwise-{seed}';m=models[name];dual={}
                for arm in ('pairwise','incidence'):
                    bank=schema.bank(t,arm,dev,'matched')
                    cond=m.encoder.frozen_bank(bank);out=run_bulk(m,d,cond,dev);dual[arm]=(cond,out)
                c,(cs,ct,cr)=dual['pairwise'];v,(ds,dt,dr)=dual['incidence']
                changed=[int(((one['pointers']!=other['pointers']).any(-1)|(one['active']!=other['active'])|(one['rows']!=other['rows']).any(-1)).any(1).sum()) for one,other in zip(cs,ds)]
                matched[tid][name]=dict(table_max_abs=float((c-v).abs().max()),token_max_abs=float(np.abs(ct-dt).max()),
                    changed_run1_graphs=changed[0],changed_run2_graphs=changed[1],
                    semantic_decision_differences=int((cr.argmax(-1)!=dr.argmax(-1)).sum()))
            print(tid,{n:r['groups']['all']['nonempty_complete'] for n,r in reports[tid].items()},flush=True)
    result=dict(fits=fits,reports=reports,timings=timed,matched=matched,geometry=sizes,split_sha256=digest(MANIFEST))
    (args.root/'results.json').write_text(json.dumps(result,separators=(',',':'))+'\n')


if __name__=='__main__':main()

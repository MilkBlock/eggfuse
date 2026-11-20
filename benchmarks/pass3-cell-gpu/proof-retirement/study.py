"""Retire pending children in a frozen generated DAG on the real GPU executor at original Run boundaries."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
from statistics import median
import sys
import tempfile
from time import perf_counter_ns
from unittest.mock import patch

import numpy as np
import torch

HERE=Path(__file__).resolve().parent
GPU=HERE.parent
sys.path.insert(0,str(GPU/'recurrent-generator'))
from capture import inputs, load_catalog, read, verify
from compound_model import pair_joins
from feedback_study import bind_session
import run as engine


def replace_once(text,old,new):
    if text.count(old)!=1:
        raise ValueError(f'GPU capture point changed: {old!r}')
    return text.replace(old,new)


@contextmanager
def retirement_executor(batch):
    # Only the invalidation policy changes. Keep the production parser, verifier, graph,
    # original scheduler and exact fallback. No source reference is installed in the worker.
    with tempfile.TemporaryDirectory() as temp:
        overlay=Path(temp)
        (overlay/'executor.metal').symlink_to(GPU/'executor.metal')
        module=overlay/'recurrent-generator';module.mkdir()
        real=GPU/'recurrent-generator'
        for filename in ('features.metal','actor.metal','compound_replay.metal'):
            (module/filename).symlink_to(real/filename)
        source=(real/'compound.metal').read_text()
        source=replace_once(source,'kernel void compound_resume(',f'#define RETIRE_BATCH {int(batch)}\n'+(HERE/'retire.metal').read_text()+'\nkernel void compound_resume(')
        source=replace_once(source,'    int live=state[75],keep=0;', '    int live=state[75],keep=0;\n    retire_pending(state,meta,live);')
        source=replace_once(source,'int id=queue[i];device CompoundClaim &c=claims(meta)[id];','int id=queue[i];device CompoundClaim &c=claims(meta)[id];\n        if(c.status!=2)continue;')
        (module/'compound.metal').write_text(source)
        with patch.object(engine,'HERE',overlay):yield


def edit_parent(raw,claims):
    independent=(claims[:,0,7]>0)&(claims[:,1,7]>0)&(claims[:,0,2]!=claims[:,1,2])
    choices=np.flatnonzero(independent)
    if not len(choices):return None,None
    t=int(choices[0]);lane=int(claims[t,0,0])
    out=raw.copy();out[t,lane,9]=0
    return out,dict(issue_run=t+1,parent_row=lane,eligible_forks=len(choices))


def one(a,case,seed,scenario,source,raw,joins,entries,image,gold):
    streams={};sessions={};result={}
    with np.load(gold/'output.npz') as g:truth={k:g[k] for k in ('rhs','runs','writes','resumes')}
    model=read(a.training/f'train-{seed}'/'policy.json')
    for name in ('batch','dependencies'):
        dest=a.out/f'{case}-{seed}-{scenario}-{name}'
        cfg=dict(catalog=entries,rows=2,ranks=8,hidden=8,waves=2,weights=model['roots'],
                 compound=dict(joins=joins,child=model['child'],batch=True,replay=raw))
        with retirement_executor(name=='batch'):
            engine.execute(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,dest,
                           neural=cfg,measure_resident=bind_session(sessions,name))
        verify(dest,gold,image)
        with np.load(dest/'neural-output.npz') as n,np.load(dest/'compound-output.npz') as z:
            np.testing.assert_array_equal(n['raw'],raw)
            claims=z['claims'];roots=n['rhs_ordinal'][:,:2]
        streams[name]=claims,roots
        status=claims[:,:,8]
        issue=tickets=0;invalid=[]
        for t,c in zip(*np.nonzero(np.isin(status,[3,7,8]))):
            p=claims[t,c]
            if p[8]==7:
                assert p[5]==t+1 and roots[t,p[0]]==0;issue+=1
            if p[8]==3:
                assert t+1<p[5] and p[4]>0 and p[6]!=p[4];tickets+=1
            if p[8]==8:
                sibling=claims[t,1-c]
                assert sibling[5]==p[5] and sibling[8] in (3,7)
            invalid.append([int(t)+1,int(c),int(p[8]),int(p[5]),int(p[6])])
        winners=np.r_[roots[roots>0],claims[:,:,7][status==6]]
        assert len(set(map(int,winners)))==len(winners)
        result[name]=dict(runs=len(roots),rhs=len(truth['rhs']),roots=int((roots>0).sum()),children=int((status==6).sum()),
                          exact=len(truth['rhs'])-len(winners),orphan=issue,stale=tickets,collateral=int((status==8).sum()),
                          stale_hidden=int(((status==3)&(claims[:,:,6]<0)).sum()),
                          stale_republished=int(((status==3)&(claims[:,:,6]>=0)).sum()),
                          route_attempts=int(claims[:,:,9].sum()),invalidations=invalid,ms=[],source_aligned=True)
    for trial in range(6):
        for name in (('batch','dependencies') if trial%2==0 else ('dependencies','batch')):
            reset,infer,buf=sessions[name];reset();torch.mps.synchronize()
            begin=perf_counter_ns();infer();torch.mps.synchronize()
            result[name]['ms'].append((perf_counter_ns()-begin)/1e6)
            state=buf['state'].cpu().tolist();assert state[7] and not state[5]
            for k,i in [('runs',11),('rhs',9),('writes',10),('resumes',16)]:
                actual,expected=buf[k][:state[i]].cpu().numpy(),truth[k]
                if k=='rhs':
                    np.testing.assert_array_equal(actual[:,:2],expected[:,:2]);actual,expected=actual[:,4:],expected[:,4:]
                np.testing.assert_array_equal(actual,expected)
    for v in result.values():v['median_ms']=median(v['ms'])
    coarse,precise=streams['batch'][0],streams['dependencies'][0]
    np.testing.assert_array_equal(streams['batch'][1],streams['dependencies'][1])
    other=(coarse[:,:,8]==8)
    # Each extra withdrawal must be triggered by a failed sibling at the same boundary.
    result['collateral_that_would_win']=int((other&(precise[:,:,7]>0)).sum())
    result['unrelated_child_winner_differences']=int(((coarse[:,:,7]!=precise[:,:,7])&~other).sum())
    if scenario=='observed':
        np.testing.assert_array_equal(precise[:,:,7],source[:,:,7])
    return result


def main(a):
    a.out.mkdir(parents=True,exist_ok=False)
    donor=a.ref/'sum-bits/program.json';joins=pair_joins(read(donor)); report={}
    for n in a.cases:
        image,p,gold=inputs(a.corpus,a.ref,n);entries=load_catalog(image,p,donor)
        for seed in a.seeds:
            folder=a.paired/f'{n}-{seed}-batch'
            with np.load(folder/'compound-output.npz') as c,np.load(folder/'neural-output.npz') as z:
                claims=c['claims'];original=z['raw']
            injected,fork=edit_parent(original,claims)
            for scenario,raw in [('observed',original),('reject-parent',injected)]:
                if raw is None:continue
                data=one(a,n,seed,scenario,claims,raw,joins,entries,image,gold)
                if scenario=='reject-parent':data['fork']=fork
                report[f'{n}/{seed}/{scenario}']=data
                (a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')
                print(n,seed,scenario,data['dependencies']['stale'],data['batch']['collateral'],data['collateral_that_would_win'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','reader','training','paired','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','gemm-bias-relu','stable-argmax'])
    p.add_argument('--seeds',type=int,nargs='+',default=[1703,1709])
    with torch.inference_mode():main(p.parse_args())

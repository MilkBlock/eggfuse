"""Vary neural waves within each original Run; an all-null wave can stop proposing on device."""
import argparse
import json
from pathlib import Path
from statistics import median
from time import perf_counter_ns

import numpy as np
import torch

from capture import execute,inputs,load_catalog,read,verify
from feedback_study import bind_session
from provenance import validate


def collect(a):
    a.out.mkdir(parents=True,exist_ok=False)
    result={}
    for case in a.cases:
        image,program,gold=inputs(a.corpus,a.ref,case)
        entries=load_catalog(image,program,a.ref/'sum-bits/program.json')
        with np.load(a.capture/case/'training.npz') as z:
            positive=z['positive'];features=z['features']
        with np.load(gold/'output.npz') as z:
            source={k:z[k] for k in ('runs','rhs','writes','resumes')}
        for seed in a.seeds:
            checkpoint=read(a.capture/f'train-{seed}-2/actor.json')
            sessions,report={},{}
            for name,waves,adaptive in [('one',1,False),('two',2,False),('four',4,False),
                                        ('eight',8,False),('sixteen',16,False),('null-stop',16,True)]:
                cfg=dict(catalog=entries,weights=checkpoint['weights'],rows=2,ranks=8,hidden=8,receipt_head=True,
                         feedback=2,waves=waves,stop_on_null=adaptive)
                dest=a.out/f'{case}-{seed}-{name}'
                execute(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,dest,
                        neural=cfg,measure_resident=bind_session(sessions,name))
                verify(dest,gold,image);won=validate(dest,entries)
                with np.load(dest/'neural-output.npz') as z:
                    raw=z['raw'];status=z['verdict'][:,:,0];wins=z['committed']
                with np.load(dest/'output.npz') as z:counts=z['runs'][:,1]
                active=(status!=0).reshape(len(counts),waves,2).any(2)
                stops=(~active).any(1) if adaptive else np.zeros(len(counts),dtype=bool)
                used=np.where(stops,(~active).argmax(1)+1,waves)
                if adaptive:
                    skipped=np.arange(waves)[None]>=used[:,None]
                    assert not active[skipped].any() and not raw.reshape(len(counts),waves,2,-1)[skipped].any()
                hit=np.zeros_like(positive)
                for t,row in zip(*np.nonzero(wins)):
                    leaf,addr,rank=map(int,raw[t,row,-4:-1]);action=(leaf-1)*8+rank-1
                    assert features[t,action,0]==addr-1
                    hit[t,action]=True
                pending=(positive & ~hit).sum(1)
                report[name]=dict(waves=waves,adaptive=adaptive,issued=used.sum().item()*2,
                    actual_forward_waves=int(used.sum()),raw=int((status!=0).sum()),accepted=int((status==1).sum()),
                    rejected=int((status==2).sum()),duplicate=int((status==3).sum()),committed=won,
                    exact_rhs=int(counts.sum())-won,rhs=int(counts.sum()),nonempty=int((counts>0).sum()),
                    full_nonempty=int(((counts>0)&(counts==wins.sum(1))).sum()),per_wave=wins.reshape(-1,waves,2).sum(0).tolist(),
                    reference_winner_bound=int(np.minimum(positive.sum(1),2*waves).sum()),unclaimed_at_stop=int(pending[stops].sum()),
                    stops_with_unclaimed=int((stops & (pending>0)).sum()),device_kernel_slots=2048*waves,
                    ms=[],semantic_exact=True)
            arms=list(sessions)
            for trial in range(len(arms)):
                order=arms[trial:]+arms[:trial]
                for name in order:
                    reset,infer,buf=sessions[name];reset();torch.mps.synchronize()
                    start=perf_counter_ns();infer();torch.mps.synchronize()
                    report[name]['ms'].append((perf_counter_ns()-start)/1e6)
                    state=buf['state'].cpu().tolist();assert state[7] and not state[5]
                    assert state[9]==report[name]['rhs']
                    for field,idx in [('runs',11),('rhs',9),('writes',10),('resumes',16)]:
                        actual,reference=buf[field][:state[idx]].cpu().numpy(),source[field]
                        if field=='rhs':
                            np.testing.assert_array_equal(actual[:,:2],reference[:,:2])
                            actual,reference=actual[:,4:],reference[:,4:]
                        np.testing.assert_array_equal(actual,reference)
            for v in report.values():v['median_ms']=median(v['ms'])
            result[f'{case}/{seed}']=report
            (a.out/'results.json').write_text(json.dumps(result,indent=1)+'\n')
            print(case,seed,[(k,v['committed'],round(v['median_ms'])) for k,v in report.items()],flush=True)
            sessions.clear()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','reader','capture','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product'])
    p.add_argument('--seeds',nargs='+',type=int,default=[1703,1709])
    with torch.inference_mode():collect(p.parse_args())

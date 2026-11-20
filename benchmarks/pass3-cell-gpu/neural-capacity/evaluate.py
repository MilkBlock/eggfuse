"""Measure model capacity and training-family diversity with one full Pass 3 verifier."""
import argparse
import json
from pathlib import Path
from statistics import median
import sys
from time import perf_counter_ns

import numpy as np
import torch

from capacity import model,packet,read
from adapter import specialize
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'recurrent-generator'))
from capture import inputs,verify
from feedback_study import bind_session


def prepare(plan,weights):
    network=model(weights['tables'],weights['rules'],weights['target']).to('mps')
    network.load_state_dict(weights['state']);network.eval()
    roots=torch.tensor(plan['roots'],device='mps',dtype=torch.int32)
    x=torch.tensor(plan['root_x'],device='mps');y=torch.tensor(plan['child_x'],device='mps')
    c=torch.tensor(plan['candidates'],device='mps',dtype=torch.int32)
    proven=torch.tensor(plan['projections'],device='mps',dtype=torch.int32)[c[:,2].long()]>=0
    def emit():
        latent,score=network(x,y,c)
        token=torch.cat([(score>=0).int()[:,None],c[:,:4]],1)
        valid=(token[:,1:]==c[:,:4]).all(1)
        check=torch.where(valid,((token[:,0]!=0)&proven).int(),-1)
        return roots,torch.cat([token,check[:,None]],1).contiguous(),latent
    return emit


def study(a):
    a.out.mkdir(parents=True,exist_ok=False)
    results={}
    for case in a.cases:
        image,program,gold=inputs(a.corpus,a.ref,case)
        p=packet(image,program)
        with np.load(gold/'output.npz') as z:source_counts=z['runs'][:,1]
        for seed in (1703,1709):
            sessions,report={},{}
            for size in (40000,160000,640000):
                for families in (2,4):
                    key=f'{size}-{families}';ck=a.training/f'{seed}-{key}'
                    weights=torch.load(ck/'weights.pt',weights_only=True)
                    emit=prepare(p,weights)
                    trained=read(ck/'record.json')
                    executor=specialize(p,emit,True,events=True)
                    out=a.out/f'{case}-{seed}-{key}'
                    executor(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,out,measure_resident=bind_session(sessions,key))
                    verify(out,gold,image)
                    with np.load(out/'forest.npz') as f,np.load(out/'output.npz') as z:
                        children=f['children'];ordinal=children[:,2]
                        positive=ordinal[ordinal>0]
                        assert len(positive)==len(np.unique(positive))
                        actual=np.bincount(z['rhs'][positive-1,0],minlength=len(source_counts)+1)[1:]
                        static=int((f['roots'][:,2]>0).sum())
                        full=int(((source_counts>0)&(source_counts==actual)).sum())
                    one=emit()[1].cpu().numpy()
                    forward=[]
                    for _ in range(20):
                        torch.mps.synchronize()
                        begin=perf_counter_ns();emit();torch.mps.synchronize();forward.append((perf_counter_ns()-begin)/1e6)
                    report[key]=dict(params=trained['parameters'],weight_bytes=trained['bytes'],training=trained,
                         scoring_positions=len(one),raw=int(one[:,0].sum()),neural_rhs=len(positive),exact_rhs=int(source_counts.sum()-len(positive)-static),
                         static_rhs=static,full_nonempty=full,nonempty=int((source_counts>0).sum()),runs=len(source_counts),
                         visits=int(children[:,5].sum()),forward_ms=forward,ms=[],semantic_exact=True)
            names=list(sessions)
            for trial in range(len(names)):
                order=names[trial:]+names[:trial]
                for key in order:
                    reset,infer,buf=sessions[key];reset();torch.mps.synchronize()
                    begin=perf_counter_ns();infer();torch.mps.synchronize()
                    report[key]['ms'].append((perf_counter_ns()-begin)/1e6)
                    state=buf['state'].cpu().tolist();assert state[7] and not state[5] and state[9]==source_counts.sum()
            for item in report.values():item['median_ms']=median(item['ms'])
            results[f'{case}/{seed}']=report
            (a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
            print(case,seed,[(k,v['neural_rhs'],round(v['median_ms'])) for k,v in report.items()],flush=True)
            sessions.clear()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','reader','training','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','gemm-bias-relu','stable-argmax'])
    with torch.inference_mode():study(p.parse_args())

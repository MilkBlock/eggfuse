"""Measure matched budgets, checkpoint/resume, terminal accuracy and synchronized latency."""
import argparse
import json
from pathlib import Path
from time import perf_counter_ns

import numpy as np
import torch
from queue_gpu import (Gate,Queue,PANELS,MAX_TICKS,device,device_plan,digest,dataset,
                       inputs,load_producer,study,upload)
from experiment import cpu

BUDGETS=(1,2,4,8,12,16,24,32,48)
LANES={**{f'fixed{k}':('fixed',k,None) for k in (1,2,4,8,16)},
       'exact':('exact',1,None),
       **{f'{arm}_{mode}':(mode,1,arm) for arm in ('ledger','blind') for mode in ('guard','raw','fair')}}


def load_gates(root,seed,dev):
    weights={None:torch.zeros(123,device=dev)};models={}
    for arm in ('ledger','blind'):
        path=root/f'{arm}-{seed}.pt';info=json.loads(path.with_suffix('.json').read_text())
        if digest(path)!=info['weight']:raise ValueError(path)
        m=Gate().to(dev);m.load_state_dict(torch.load(path,weights_only=True,map_location='cpu'));m.eval()
        weights[arm]=m.packed();models[arm]=m
    return weights,models


@torch.inference_mode()
def measure(root,producers):
    dev=device();templates,_,_,schema=study();times={}
    traces=root/'traces';traces.mkdir(parents=True,exist_ok=True)
    for seed in (1703,1709):
        model=load_producer(schema,seed,producers,dev);weights,models=load_gates(root,seed,dev)
        for t in templates:
            held=t['split']=='heldout';name=t['id'];split='heldout' if held else 'secondary'
            if not held and name not in ('rule-266','rule-267','rule-580'):continue
            d=dataset('test',t);x=upload(d,slice(None),dev);n=len(d['a'])
            table=model.encoder.encode_bank(schema.bank(t,'pairwise',dev));plan=device_plan(name,dev)
            for panel in PANELS:
                first,args=inputs(model,x,table,plan,panel,torch.arange(n,device=dev))
                archive={'manifest':args[0].cpu().numpy(),'source':args[-1].cpu().numpy(),
                         'addresses':args[-2].cpu().numpy(),**{'first_'+k:v for k,v in cpu(first).items()}}
                for lane,(mode,k,arm) in LANES.items():
                    queue=Queue(n,plan[3],dev,True);past=0
                    for budget in BUDGETS:
                        queue.advance(args,weights[arm],mode,k,budget-past,arm=='blind');past=budget
                        # No results are consumed by the next step on the CPU.
                        for field in ('state','visible','boundary'):
                            archive[f'{lane}_{budget}_{field}']=getattr(queue,field).cpu().numpy().copy()
                    same=Queue(n,plan[3],dev)
                    same.advance(args,weights[arm],mode,k,MAX_TICKS,arm=='blind')
                    for field in ('state','classes','index','visible','boundary'):
                        torch.testing.assert_close(getattr(queue,field),getattr(same,field),rtol=0,atol=0)
                    trace=queue.trace.cpu().numpy()
                    if arm is not None:
                        a=trace.reshape(-1,11);a=a[a[:,6]>=0]
                        pred=models[arm](torch.tensor(a[:,:6]/3,device=dev,dtype=torch.float32)).argmax(-1)
                        np.testing.assert_array_equal(pred.cpu().numpy(),a[:,7])
                    archive[lane+'_trace']=trace
                np.savez_compressed(traces/f'{seed}-{name}-{panel}.npz',**archive)
                if panel not in ('ordinary','late_union'):continue
                lanes=['exact','fixed4','fixed8','ledger_guard','blind_guard','blind_fair']
                ids=np.random.default_rng(1919).permutation(n)[:12]
                for j,i in enumerate([*ids[:2],*ids]):
                    for lane in lanes[j%len(lanes):]+lanes[:j%len(lanes)]:
                        mode,k,arm=LANES[lane]
                        start=perf_counter_ns();one=upload(d,slice(i,i+1),dev)
                        _,single=inputs(model,one,table,plan,panel,torch.tensor([i],device=dev))
                        q=Queue(1,plan[3],dev);q.advance(single,weights[arm],mode,k,MAX_TICKS,arm=='blind')
                        torch.mps.synchronize();ms=(perf_counter_ns()-start)/1e6
                        np.testing.assert_array_equal(q.visible.cpu().numpy()[0],archive[lane+'_48_visible'][i])
                        np.testing.assert_array_equal(q.state.cpu().numpy()[0],archive[lane+'_48_state'][i])
                        if j>=2:times.setdefault(f'{seed}/{split}/{panel}/{lane}',[]).append([int(i),ms])
            print(seed,name,flush=True)
    (root/'timings.json').write_text(json.dumps(times)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('producers',type=Path)
    a=p.parse_args();measure(a.root,a.producers)

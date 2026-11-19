"""Retain every non-timing GPU trajectory; time complete single-graph forwards separately."""
import argparse
import json
from pathlib import Path
from statistics import median
from time import perf_counter_ns

import numpy as np
import torch

from actor import PairActor
from arena import device_layout
from run_owner import run,device_plan,MODES
from train import dataset,study,device,load_producer,upload,digest
from experiment import cpu


def host(v):
    return v.detach().cpu().numpy()


@torch.inference_mode()
def evaluate(root,producers):
    dev=device();templates,_,_,schema=study();layout=device_layout(dev)
    trace_dir=root/'traces';trace_dir.mkdir(exist_ok=True)
    samples={};timing_exact={};changes={}
    for seed in (1703,1709):
        weights=root/f'actor-{seed}.pt'
        assert digest(weights)==json.loads(weights.with_suffix('.json').read_text())['weight']
        actor=PairActor().to(dev)
        actor.load_state_dict(torch.load(weights,map_location='cpu',weights_only=True));actor.eval()
        producer=load_producer(schema,seed,producers,dev)
        for t in templates:
            name=t['id'];split='heldout' if t['split']=='heldout' else 'secondary'
            if split=='secondary' and name not in ('rule-266','rule-267','rule-580'):continue
            d=dataset('test',t);x=upload(d,slice(None),dev)
            table=producer.encoder.encode_bank(schema.bank(t,'pairwise',dev));plan=device_plan(name,dev)
            for collision in (False,True):
                for at in (1,3):
                    expected={}
                    for mode in MODES:
                        first,stages,trace=run(actor,producer,x,table,plan,layout,mode,at,collision,True)
                        data={k:host(v) for k,v in trace.items()}
                        for tick,stage in stages.items():
                            data.update({f'{tick}_{k}':host(v) for k,v in stage.items()})
                        data.update({'first_'+k:v for k,v in cpu(first).items()})
                        expected[mode]={k:v for k,v in data.items() if k=='targets' or k.startswith(('0_','1_','2_','3_'))}
                        np.savez_compressed(trace_dir/f'{seed}-{name}-{int(collision)}-{at}-{mode}.npz',**data)
                    # Primary timing comparison fixes an old cursor and a live
                    # generation, with identical models and attempted work.
                    if at==3:continue
                    ix=np.random.default_rng(1616).permutation(len(d['a']))[:12]
                    for j,i in enumerate([*ix[:2],*ix]):
                        modes=('retain','forward','no_retry','forward_joint','exact_joint')
                        for mode in modes[j%len(modes):]+modes[:j%len(modes)]:
                            key=f'{seed}/{split}/{int(collision)}/{mode}'
                            start=perf_counter_ns()
                            stages,targets=run(actor,producer,upload(d,slice(i,i+1),dev),table,plan,layout,mode,at,collision)
                            torch.mps.synchronize();elapsed=(perf_counter_ns()-start)/1e6
                            if j<2:continue
                            samples.setdefault(key,[]).append(elapsed)
                            exact=all(np.array_equal(host(v)[0],expected[mode][f'{tick}_{k}'][i])
                                      for tick,s in stages.items() for k,v in s.items())
                            if not exact:raise ValueError(('single-graph source output changed',name,i,mode))
                            timing_exact[key]=timing_exact.get(key,0)+int(exact)
                            diff=not np.array_equal(host(targets)[0],expected[mode]['targets'][i])
                            changes[key]=changes.get(key,0)+int(diff)
            print(seed,name,flush=True)
    meta=dict(samples_ms=samples,median_ms={k:median(v) for k,v in samples.items()},correct=timing_exact,
              correct_per_second={k:1000*timing_exact[k]/sum(s) for k,s in samples.items()},
              composition_changed_at_batch_one=changes)
    (root/'timing.json').write_text(json.dumps(meta)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('root',type=Path);p.add_argument('producers',type=Path)
    a=p.parse_args();evaluate(a.root,a.producers)

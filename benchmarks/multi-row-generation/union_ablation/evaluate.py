"""Run the neural producer and stream union receipts on MPS, without CPU repair."""
import argparse
import json
from pathlib import Path
from statistics import median
from time import perf_counter_ns

import numpy as np
import torch

from engine import READERS, MODES, device_plan, produce, run, schedule
from experiment import dataset, study, load_producer, device, upload, cpu


def record(stages,book):
    out={'stats':book.cpu().numpy()}
    for tick,stage in stages.items():
        for k,v in stage.items():out[f'{tick}_{k}']=v.cpu().numpy()
    return out


def compare(actual,reference,index):
    for k,v in actual.items():np.testing.assert_array_equal(v,reference[k][index:index+1],err_msg=k)


@torch.inference_mode()
def evaluate(root,previous):
    dev=device()
    templates,_,_,schema=study()
    path=root/'traces';path.mkdir(parents=True,exist_ok=True)
    timings={};samples={}
    for seed in (1703,1709):
        producer=load_producer(schema,seed,previous,dev)
        for template in templates:
            held=template['split']=='heldout'
            if not held and template['id'] not in ('rule-266','rule-267','rule-580'):continue
            name=template['id'];split='heldout' if held else 'secondary'
            batch=dataset('test',template)
            x=upload(batch,slice(None),dev)
            table=producer.encoder.encode_bank(schema.bank(template,'pairwise',dev))
            plan=device_plan(name,dev)
            for observers in READERS:
                stored={}
                for policy in MODES:
                    first,stages,book=run(producer,x,table,plan,policy,observers)
                    arrays=record(stages,book)
                    arrays.update({'first_'+k:v for k,v in cpu(first).items()})
                    dest=path/f'{seed}-{name}-{observers}-{policy}.npz'
                    np.savez_compressed(dest,**arrays)
                    if policy in ('immediate','fenced','fused_fenced'):stored[policy]=arrays
                # Identical raw graph indices and balanced order across the two arms.
                indices=np.random.default_rng(1501).permutation(len(batch['a']))[:18]
                samples[name]=indices.tolist()
                lanes=[(mode,extent) for mode in ('immediate','fenced','fused_fenced') for extent in ('whole','union_read')]
                for j,i in enumerate([*indices[:4],*indices]):
                    cached=upload(batch,slice(i,i+1),dev)
                    _,token=produce(producer,cached,table)
                    torch.mps.synchronize()
                    for policy,extent in lanes[j%len(lanes):]+lanes[:j%len(lanes)]:
                        key=f'{seed}/{split}/{observers}/{policy}/{extent}'
                        start=perf_counter_ns()
                        if extent=='whole':
                            inputs=upload(batch,slice(i,i+1),dev)
                            _,stages,book=run(producer,inputs,table,plan,policy,observers)
                        else:
                            stages,book=schedule(token,cached,plan,policy,observers)
                        torch.mps.synchronize()
                        elapsed=(perf_counter_ns()-start)/1e6
                        if j>=4:timings.setdefault(key,[]).append(elapsed)
                        compare(record(stages,book),stored[policy],i)
            print(seed,name,flush=True)
    result=dict(medians={k:median(v) for k,v in timings.items()},samples_ms=timings,indices=samples)
    (root/'timing.json').write_text(json.dumps(result)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('root',type=Path);p.add_argument('producers',type=Path)
    args=p.parse_args()
    evaluate(args.root,args.producers)

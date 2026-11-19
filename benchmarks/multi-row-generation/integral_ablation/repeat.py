"""Rotate all six exact-schedule orders on each timed graph."""
import argparse
from itertools import permutations
import json
from pathlib import Path
from time import perf_counter_ns

import numpy as np
import torch
from integral import dataset,study,device,load_producer,upload,device_plan,ingress,run


@torch.inference_mode()
def main(root,producers,out):
    dev=device();ts,_,_,schema=study();results={};modes=('source','primary','integral')
    for seed in (1703,1709):
        m=load_producer(schema,seed,producers,dev)
        for t in ts:
            if t['id'] not in ('rule-134','rule-266'):continue
            name=t['id'];d=dataset('test',t);table=m.encoder.encode_bank(schema.bank(t,'pairwise',dev));plan=device_plan(name,dev)
            ids=np.random.default_rng(1818).permutation(len(d['a']))[:12];expected={}
            for mode in modes:
                with np.load(root/'traces'/f'{name}-{seed}-{mode}.npz') as z:expected[mode]=z['2_pub']
            samples={mode:[] for mode in modes};orders=list(permutations(modes))
            for rep in range(-1,6):
                batch={mode:[] for mode in modes};verify=[]
                for pos,i in enumerate(ids[:2] if rep<0 else ids):
                    for mode in orders[(pos+rep)%6]:
                        begin=perf_counter_ns();one=upload(d,slice(i,i+1),dev)
                        _,rows,admit=ingress(m,one,table,mode)
                        arena,_=run(one,plan,rows,admit,mode);torch.mps.synchronize()
                        batch[mode].append((perf_counter_ns()-begin)/1e6);verify.append((i,mode,arena.pub))
                for i,mode,pub in verify:np.testing.assert_array_equal(pub.cpu().numpy()[0],expected[mode][i])
                if rep>=0:
                    for mode in modes:samples[mode].append(batch[mode])
            def diff(a,b):return float(np.median(np.array(samples[a])-samples[b]))
            results[f'{seed}/{name}']=dict(samples_ms=samples,indices=ids.tolist(),primary_minus_source_ms=diff('primary','source'),
                integral_minus_primary_ms=diff('integral','primary'))
    out.write_text(json.dumps(results,indent=1)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('root','producers','out'):p.add_argument(k,type=Path)
    a=p.parse_args();main(a.root,a.producers,a.out)

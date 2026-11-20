"""Interleave normal MPS dispatches from independent, already-resident executor states."""
import argparse
from itertools import permutations
import json
from pathlib import Path
from statistics import median
import sys
from time import perf_counter_ns

import numpy as np
import torch

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
from run import execute


@torch.inference_mode()
def measure(root,address,out):
    results={}
    for case in ('sum-bits','dot-product'):
        sessions={}
        with np.load(root/f'release-{case}'/'output.npz') as z:
            expected={k:z[k] for k in ('rhs','writes','resumes','runs')}
        for mode in (0,2,4):
            def retain(infer,buf,_constants,_width,_steps,_lanes):
                seeds={k:buf[k].clone() for k in ('state','meta','dyn','head','wm')}
                def reset():
                    for k,v in seeds.items():buf[k].copy_(v)
                    for k in ('regs','count','rhs','writes','runs','resumes'):buf[k].zero_()
                sessions[mode]=reset,infer,buf
            execute(root/f'release-input-{case}'/'device.json',address,root/'ports-1703.pt',2048,2,
                    out/f'warm-{case}-{mode}',measure_resident=retain,hot_filter=mode)
        records={m:[] for m in sessions}
        for order in permutations((0,2,4)):
            for mode in order:
                reset,infer,buf=sessions[mode]
                torch.mps.synchronize();start=perf_counter_ns();reset();torch.mps.synchronize()
                begin=perf_counter_ns();infer();torch.mps.synchronize();end=perf_counter_ns()
                state=buf['state'].cpu().tolist();assert not state[5] and state[7]
                for key,j in [('rhs',9),('writes',10),('resumes',16),('runs',11)]:
                    got=buf[key][:state[j]].cpu().numpy();want=expected[key]
                    if key=='rhs':
                        np.testing.assert_array_equal(got[:,:2],want[:,:2]);got=got[:,4:];want=want[:,4:]
                    np.testing.assert_array_equal(got,want)
                records[mode].append({'ms':(end-begin)/1e6,'reset_ms':(begin-start)/1e6})
        results[case]={m:dict(samples=v,median_ms=median(r['ms'] for r in v)) for m,v in records.items()}
        print(case,[(m,results[case][m]['median_ms']) for m in records],flush=True)
    (out/'warm-paired.json').write_text(json.dumps(results,indent=1)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('root','address','out'):p.add_argument(k,type=Path)
    a=p.parse_args();measure(a.root,a.address,a.out)

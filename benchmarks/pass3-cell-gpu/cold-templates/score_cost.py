"""Measure the exact native child scorer on archived parent tokens, one GPU grid for the complete stream."""
from pathlib import Path
from statistics import median
from time import perf_counter_ns

import numpy as np
import torch


def measure(native,entries,raw):
    code=(Path(__file__).resolve().parent.parent/'recurrent-generator/compound.metal').read_text()
    body=code[code.index('    int row_weights='):code.index('    for(int h=0;h<stride;h++)trace')]
    read='int status=COM_BATCH?0:receipts[4*((run-1)*NEURAL_SLOTS+peer)];'
    if body.count(read)!=1:raise ValueError('existing scorer receipt ABI changed')
    body=body.replace(read,'int status=0;')
    joins=native['joins']
    source='''#include <metal_stdlib>
using namespace metal;
#define COM_MASK_PARENT 0
#define NEURAL_RANKS 8
'''
    source+=f'#define COM_JOINS {len(joins)}\nconstant int compound_joins[]={{'+','.join(str(x) for j in joins for x in j)+'};\n'
    source+='constant int neural_catalog[]={'+','.join(str(x) for e in entries for x in e)+'};\n'
    source+='''kernel void score(device const float *weights,device const float *all_parents,device float *all_children,
                                 uint gid [[thread_position_in_grid]]){
    int run=gid/2+1,lane=gid%2,stride=12;
    device const float *parents=all_parents+24*(run-1);device float *child=all_children+24*(run-1);
'''+body+'\n}\n'
    before=perf_counter_ns()
    lib=torch.mps.compile_shader(source)
    roots=torch.tensor(raw[:,:2].copy(),device='mps');w=torch.tensor(native['child'],device='mps',dtype=torch.float32)
    out=torch.empty_like(roots)
    lib.score(w,roots,out,threads=2*len(raw));torch.mps.synchronize()
    first=(perf_counter_ns()-before)/1e6
    got=out.cpu().numpy();want=raw[:,2:]
    np.testing.assert_array_equal(got[:,:,8:],want[:,:,8:]);error=float(np.max(np.abs(got[:,:,:8]-want[:,:,:8])))
    assert error<1e-5,error
    samples=[]
    for _ in range(20):
        start=perf_counter_ns();lib.score(w,roots,out,threads=2*len(raw));torch.mps.synchronize()
        samples.append((perf_counter_ns()-start)/1e6)
    leaves=raw[:,:2,8].astype(int)-1
    compatible=2*sum(int((leaves==l).sum()) for _,l,_,r in joins if entries[r][0]>=0)
    return dict(root_tokens=2*len(raw),active_roots=int((leaves>=0).sum()),scanned=2*int((leaves>=0).sum())*len(joins),
                compatible_dot_products=compatible,first_device_setup_and_score_ms=first,
                resident_batch_ms=samples,median_batch_ms=median(samples),
                median_ns_per_output_token=median(samples)*1e6/(2*len(raw)),
                discrete_difference=0,max_latent_difference=error)

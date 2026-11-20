"""Exercise the actual device scalar routine at integer and FP32 representation boundaries."""
import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np
import torch

from lower import PRIMS


def reference(op,x,y):
    low,high=-(1<<63),(1<<63)-1
    if op in (0,15):value=0 if x!=y else None
    elif op in (1,5):
        if not y or (x==low and y==-1):value=None
        else:
            div=(abs(x)//abs(y))*(-1 if (x<0)!=(y<0) else 1)
            value=x-y*div if op==1 else div
    elif op in (2,3,4):value=(x*y,x+y,x-y)[op-2]
    elif 6<=op<=9:value=0 if (x<y,x<=y,x>y,x>=y)[op-6] else None
    elif op==10:value=int(bool(x) and bool(y))
    elif op==11:value=int(x<y)
    elif PRIMS[op]=='min':value=min(x,y)
    elif PRIMS[op]=='max':value=max(x,y)
    elif op==14:value=int(bool(x) or bool(y))
    else:raise ValueError(op)
    return (1,value) if value is not None and low<=value<=high else (0,0)


def main(out):
    points=[-(1<<63),-(1<<63)+1,-(1<<28),-(1<<24)-1,-(1<<24),-3,-1,0,1,2,3,
            1<<24,(1<<24)+1,(1<<24)+2,1<<28,(1<<63)-2,(1<<63)-1]
    cases=[(i,x,y) for i in range(len(PRIMS)) for x in (points if i not in (10,14) else (0,1))
           for y in (points if i not in (10,14) else (0,1))]
    wanted=np.array([reference(*v) for v in cases],np.int64)
    inputs=torch.tensor(cases,dtype=torch.int64,device='mps')
    program=Path(__file__).with_name('executor.metal').read_text()
    code=program[program.index('inline bool exact_prim'):program.index('inline bool eval_op')]
    records={}
    for i,name in enumerate(('integer','guarded','lossy')):
        lib=torch.mps.compile_shader(f'#include <metal_stdlib>\nusing namespace metal;\n#define SCALAR_MODE {i}\n#define PROFILE_PRIMS 1\n'+code)
        state=torch.zeros(51,dtype=torch.int32,device='mps')
        ans=torch.empty((len(cases),2),device='mps',dtype=torch.int64)
        lib.primitive_probe(inputs,ans,state,threads=len(cases))
        got=ans.cpu().numpy()
        bad=np.flatnonzero(np.any(got!=wanted,axis=-1))
        if name!='lossy' and len(bad):raise ValueError((name,cases[bad[0]],got[bad[0]],wanted[bad[0]]))
        records[name]=dict(cases=len(cases),wrong=len(bad),by_op=Counter(PRIMS[cases[j][0]] for j in bad),
                           float_calls=state[35:51].cpu().tolist(),sample=[dict(args=cases[j],wanted=wanted[j].tolist(),got=got[j].tolist()) for j in bad[:4]])
    if not records['lossy']['wrong']:raise ValueError('lossy positive control unexpectedly passed')
    out.parent.mkdir(exist_ok=True);out.write_text(json.dumps(records,indent=2)+'\n')
    print({k:(v['cases'],v['wrong']) for k,v in records.items()})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);main(p.parse_args().out)

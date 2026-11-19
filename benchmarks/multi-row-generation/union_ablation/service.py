"""Time only the prepared Metal union/read submissions on identical fresh states."""
import argparse
from itertools import permutations
import json
from pathlib import Path
from statistics import median
from time import perf_counter_ns

import numpy as np
import torch

from engine import READERS, device_plan, kernels
from experiment import dataset, study, device, upload


def commands(x,plan,mode,readers):
    req,ports,phase,receipt,ext,ends=(x[2],*x[4:])
    words,nodes,pair,size=plan
    requests=torch.stack((nodes[req[...,0].long(),ports[...,0].long()],
                          nodes[req[...,2].long(),ports[...,1].long()]),-1).contiguous()
    empty=torch.full((len(req),2),-1,dtype=torch.int32,device=req.device)
    events=[empty]
    for owner in (0,1):
        events.append(torch.where(((phase[:,owner]>=1)&receipt[:,owner].bool())[:,None],pair[owner],empty))
    bridge=torch.stack([nodes[ext[:,col].long(),ends[:,i].long()] for i,col in enumerate((1,3))],-1)
    events.append(torch.where(ext[:,:1].bool(),bridge,empty))
    pending=[];issued=[]
    for tick,item in enumerate(events):
        pending.append(item)
        read=tick in readers
        if mode=='fused_fenced' and not read:continue
        count=len(pending)
        event=torch.stack(pending,dim=1) if count>1 else item
        issued.append((tick,event,count,int(mode=='immediate' or read)+2*int(read)))
        pending.clear()
    return requests,issued


def measure_case(x,plan,readers,references,indices):
    words,_,_,n=plan
    dev=words.device;batch=len(indices)
    policies=('immediate','fenced','fused_fenced')
    streams={p:commands(x,plan,p,readers) for p in policies}
    lib=kernels();output={p:{'stream_ms':[],'wall_ms':[]} for p in policies}
    for i,order in enumerate([policies,*permutations(policies),*permutations(policies)]):
        for mode in order:
            requests,issued=streams[mode]
            # All batch data, output buffers and initial classes are ready before the interval.
            cls=torch.arange(n,device=dev,dtype=torch.int32).repeat(batch,1)
            book=torch.zeros((batch,23),device=dev,dtype=torch.int32)
            sinks=[torch.empty((batch,10),device=dev,dtype=torch.int32) for _ in issued]
            start=torch.mps.Event(enable_timing=True);end=torch.mps.Event(enable_timing=True)
            torch.mps.synchronize()
            begin=perf_counter_ns();start.record()
            for (tick,event,count,flags),sink in zip(issued,sinks):
                lib.advance(cls,book,event,requests,words,sink,flags,count,threads=batch,
                            arg_casts={6:'int32',7:'int32'})
            end.record();end.synchronize()
            wall=(perf_counter_ns()-begin)/1e6
            stream=start.elapsed_time(end)
            for (tick,*_),sink in zip(issued,sinks):
                if tick in readers:
                    got=sink.cpu().numpy()
                    np.testing.assert_array_equal(got[:,:6],references[mode][f'{tick}_classes'][indices])
                    np.testing.assert_array_equal(got[:,6:],references[mode][f'{tick}_legality'][indices])
            np.testing.assert_array_equal(book[:,:12].cpu().numpy(),references[mode]['stats'][indices])
            if i:
                output[mode]['stream_ms'].append(stream)
                output[mode]['wall_ms'].append(wall)
    return {name:dict(samples=times,submissions=len(streams[name][1]),
                      medians={k:median(v) for k,v in times.items()}) for name,times in output.items()}


@torch.inference_mode()
def main(root,out):
    dev=device();templates=study()[0]
    all_results={}
    for t in templates:
        if t['id'] not in ('rule-134','rule-266'):continue
        d=dataset('test',t);plan=device_plan(t['id'],dev)
        for obs in ('finish','each'):
            refs={}
            for mode in ('immediate','fenced','fused_fenced'):
                p=root/'traces'/f"1703-{t['id']}-{obs}-{mode}.npz"
                with np.load(p,allow_pickle=False) as z:refs[mode]=dict(z)
            for batch in (1,128,4096):
                ids=(np.arange(batch)+6)%len(d['a'])
                x=upload(d,ids,dev)
                key=f"{t['id']}/{obs}/{batch}"
                all_results[key]=measure_case(x,plan,READERS[obs],refs,ids)
                print(key,flush=True)
    out.write_text(json.dumps(all_results,indent=1)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('root',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();main(a.root,a.output)

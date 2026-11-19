"""Sample real process and MPS allocations in an isolated interpreter per policy."""
import argparse
import json
import os
from pathlib import Path
import resource
import subprocess
import sys


def worker(root,producers,mode,fixed):
    import numpy as np
    import torch
    from integral import Arena, dataset, study, device, load_producer, upload, device_plan, ingress, run
    dev=device();ts,_,_,schema=study();t=next(t for t in ts if t['id']=='rule-266')
    d=dataset('test',t);p=load_producer(schema,1703,producers,dev);plan=device_plan(t['id'],dev)
    with torch.inference_mode():
        table=p.encoder.encode_bank(schema.bank(t,'pairwise',dev))
        x=upload(d,slice(None),dev);_,inputs,admit=ingress(p,x,table,mode)
        run(x,plan,inputs,admit,mode)
        # Tile the same real streams, not a single enlarged e-graph.
        x=tuple(v.repeat((128,)+(1,)*(v.ndim-1)) for v in x)
        inputs=inputs.repeat(128,1,1);admit=admit.repeat(128,1)
        torch.mps.synchronize();torch.mps.empty_cache()
        arena=Arena(x,plan,fixed=fixed)
        def capture():
            torch.mps.synchronize()
            rss=int(subprocess.check_output(['ps','-o','rss=','-p',str(os.getpid())]))*1024
            return dict(process_rss=rss,process_peak_rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                        mps_tensor=torch.mps.current_allocated_memory(),mps_driver=torch.mps.driver_allocated_memory(),
                        arena_page_bytes=sum(v.numel()*v.element_size() for v in arena.pages))
        readings=[capture()];previous=[]
        for stage in range(3):
            arena.step(stage,x,inputs,admit,mode)
            readings.append(capture())
            addresses=[v.data_ptr() for v in arena.pages]
            assert addresses[:len(previous)]==previous
            previous=addresses
        with np.load(root/'traces'/f'rule-266-1703-{mode}.npz') as z:
            expected=torch.as_tensor(z['2_pub'],device=dev)
            assert (arena.pub.reshape(128,128,16,14)==expected[None]).all().item()
        print(json.dumps(dict(mode=mode,fixed=fixed,graphs=len(inputs),stages=readings)))


def measure(root,producers,out):
    samples=[]
    modes=('source','primary','integral')
    for repeat in range(3):
        for mode in modes[repeat:]+modes[:repeat]:
            for fixed in (False,True) if repeat%2==0 else (True,False):
                cmd=[sys.executable,__file__,str(root),str(producers),str(out),'--worker',mode]
                if fixed:cmd+=['--fixed']
                samples.append(json.loads(subprocess.check_output(cmd,text=True)))
    out.write_text(json.dumps(samples,indent=1)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ('root','producers','out'):p.add_argument(key,type=Path)
    p.add_argument('--worker',choices=('source','primary','integral'))
    p.add_argument('--fixed',action='store_true');a=p.parse_args()
    if a.worker:worker(a.root,a.producers,a.worker,a.fixed)
    else:measure(a.root,a.producers,a.out)

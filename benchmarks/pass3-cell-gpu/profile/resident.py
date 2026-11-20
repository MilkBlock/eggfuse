"""Benchmark fresh mutable state over the same GPU-resident inputs and compiled pipelines."""
import argparse
import json
from pathlib import Path
import sys
from time import perf_counter_ns

import numpy as np
import torch

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
from run import execute

def main(args):
    args.out.mkdir(parents=True,exist_ok=True)
    def profile(infer,buf,constants,width,steps,lanes):
        names=('state','regs','meta','dyn','head','wm','count','rhs','writes','runs','resumes')
        # Snapshot the injected source graph on-device before any source Run.
        seeds={k:buf[k].clone() for k in ('state','meta','dyn','head','wm')}
        def reset():
            for k in names:
                if k in seeds:buf[k].copy_(seeds[k])
                else:buf[k].zero_()
        if args.capture:
            cap=args.out/'ingress';cap.mkdir(exist_ok=True)
            specs={}
            for k,v in buf.items():
                specs[k]=dict(bytes=v.numel()*v.element_size(),shape=list(v.shape),itemsize=v.element_size())
                if k in ('prog','literal',*seeds):
                    v.cpu().numpy().tofile(cap/(k+'.bin'))
            (cap/'profile.metal').write_text(constants+'\n'+(HERE/'executor.metal').read_text())
            (cap/'layout.json').write_text(json.dumps(dict(buffers=specs,threads=width,steps=steps,lanes=lanes)))
        reference=args.root/f'release-{args.case}'/'output.npz'
        with np.load(reference) as z:
            want={k:z[k] for k in ('runs','resumes','rhs','writes')}
        samples=[]
        for i in range(args.repeat+1):
            torch.mps.synchronize();tick=perf_counter_ns();reset();torch.mps.synchronize();beg=perf_counter_ns()
            infer();torch.mps.synchronize();end=perf_counter_ns()
            st=buf['state'].cpu().tolist()
            if st[5] or not st[7]:raise ValueError(st)
            for k,n in [('runs',st[11]),('resumes',st[16]),('rhs',st[9]),('writes',st[10])]:
                data=buf[k][:n].cpu().numpy()
                if k=='rhs':
                    # Lane/pivot may change on a duplicate with identical input slots.
                    np.testing.assert_array_equal(data[:,:2],want[k][:,:2])
                    data=data[:,4:];expected=want[k][:,4:]
                else:expected=want[k]
                np.testing.assert_array_equal(data,expected,err_msg=k)
            samples.append(dict(reset_ms=(beg-tick)/1e6,inference_ms=(end-beg)/1e6,verified_runs=st[11]))
            print(args.case,i,samples[-1],flush=True)
        (args.out/'resident.json').write_text(json.dumps(dict(warmup=samples[0],samples=samples[1:]),indent=1)+'\n')
        reset();torch.mps.synchronize()
    execute(args.root/f'release-input-{args.case}'/'device.json',args.address,args.root/'ports-1703.pt',
            2048,2,args.out,measure_resident=profile,hot_filter=args.freshness,index_repair=args.index_repair)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('root','address','out'):p.add_argument(k,type=Path)
    p.add_argument('case',choices=('sum-bits','dot-product'))
    p.add_argument('--capture',action='store_true');p.add_argument('--repeat',type=int,default=3)
    p.add_argument('--index-repair',action='store_true');p.add_argument('--freshness',type=int,choices=(0,1,2,3,4),default=0);main(p.parse_args())

"""Measure whether the same dynamic GPU verifier benefits from syncing only scheduled unresolved subscriptions."""
import argparse
import json
import os
from pathlib import Path
from statistics import median
import subprocess
from time import perf_counter_ns

import torch
from study import native_cli,native_stats,Generator,inputs,read,write,words,readline


def study(a):
    a.out.mkdir(parents=True,exist_ok=False);reports={}
    for case in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax'):
        image,p,_=inputs(a.corpus,a.ref,case)
        gold=a.native/f'{case}-native-reference'
        if not gold.is_dir():gold=a.paired/f'{case}-native-reference'
        for seed in (1703,1709):
            stem=f'{case}-{seed}';source=a.paired/f'{stem}-sealed.json'
            model=Generator(p,image,torch.load(a.weights/f'policy-{seed}.pt',weights_only=True),'mps')
            def emit():
                _,token,_=model.emit();token[:,5]=torch.where((token[:,0]!=0)&(token[:,5]==0),-2,token[:,5])
                return token.cpu().contiguous().numpy().astype('<i4',copy=False).tobytes()
            data={};procs={}
            try:
                for mode in ('delta','ready'):
                    dest=a.out/f'{stem}-{mode}'
                    native_cli(a.build/'runtime',p,dest,['--precomputed-forest',str(source)],mode)
                    data[mode]=dict(audit=native_stats(dest,gold,True),samples=[])
                    procs[mode]=subprocess.Popen([str(a.build/'session'),str(p),str(source)],
                        env=dict(os.environ,EGGFUSE_PROOF_SIDECAR=mode),stdin=subprocess.PIPE,stdout=subprocess.PIPE)
                assert data['ready']['audit']['child_ordinals']==data['delta']['audit']['child_ordinals']
                state=None
                for t in range(8):
                    for mode in (('ready','delta') if t%2==0 else ('delta','ready')):
                        proc=procs[mode];assert readline(proc)=='ready'
                        start=perf_counter_ns();buf=emit();words(proc,buf);r=json.loads(readline(proc));elapsed=(perf_counter_ns()-start)/1e6
                        assert r['children']==data[mode]['audit']['neural_children']
                        digest=readline(proc)
                        if state is None:state=digest
                        assert digest==state
                        data[mode]['samples'].append(dict(ms=elapsed,sidecar=r['sidecar']))
                for proc in procs.values():assert readline(proc)=='ready';words(proc,b'');assert proc.wait()==0
            finally:
                for proc in procs.values():
                    if proc.poll() is None:proc.kill();proc.wait()
            for v in data.values():v['median_ms']=median(s['ms'] for s in v['samples'])
            reports[f'{case}/{seed}']=data;write(a.out/'results.json',reports)
            print(case,seed,[(k,v['audit']['sidecar']['launches'],v['audit']['sidecar']['source_scans'],round(v['median_ms'])) for k,v in data.items()],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','weights','build','native','paired','out'):p.add_argument(k,type=Path)
    with torch.inference_mode():study(p.parse_args())

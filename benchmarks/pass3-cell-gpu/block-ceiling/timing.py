"""Time all three source-scheduled executors without the work counters."""
from itertools import permutations
import argparse,json
from pathlib import Path
from statistics import median
from time import perf_counter_ns
import numpy as np
import torch
from replay import execute,plans

@torch.inference_mode()
def measure(ref,weights,out):
    out.mkdir(parents=True,exist_ok=False);report={}
    for case in ('sum-bits','dot-product'):
        plan,info=plans(ref,case,'sum-bits');sessions={};results={}
        with np.load(ref/f'release-{case}/output.npz') as z:
            expected={k:z[k] for k in ('rhs','writes','resumes','runs','rows','meta','parents')}
        widths=[len(t['schema']) for t in json.loads((ref/f'release-input-{case}/ingress.json').read_text())['tables']]
        for name,policy in [('source',None),('blocks',dict(plan,select=True,notify=False)),('notifications',dict(plan,select=True,notify=True))]:
            def retain(infer,buf,*_):
                seed={k:buf[k].clone() for k in ('meta','dyn','state','head','wm')}
                def reset():
                    for k,v in seed.items():buf[k].copy_(v)
                    for k in ('regs','count','rhs','writes','runs','resumes'):buf[k].zero_()
                sessions[name]=reset,infer,buf
            dest=out/f'{case}-{name}';execute(ref/f'release-input-{case}/device.json',weights,ref/'ports-1703.pt',2048,2,dest,
                                             measure_resident=retain,block_study=policy)
            with np.load(dest/'output.npz') as z:
                for k,w in expected.items():
                    if k=='rhs':
                        np.testing.assert_array_equal(z[k][:,:2],w[:,:2]);np.testing.assert_array_equal(z[k][:,4:],w[:,4:])
                    elif k=='rows':
                        for t,n in enumerate(widths):
                            at=expected['meta'][:,0]==t
                            np.testing.assert_array_equal(z[k][at,:n],w[at,:n])
                    else:np.testing.assert_array_equal(z[k],w)
            results[name]=[]
        for order in permutations(sessions):
            for name in order:
                reset,infer,buf=sessions[name];reset();torch.mps.synchronize()
                start=perf_counter_ns();infer();torch.mps.synchronize();ms=(perf_counter_ns()-start)/1e6
                state=buf['state'].cpu().tolist();assert not state[5] and state[7]
                for k,j in [('rhs',9),('writes',10),('resumes',16),('runs',11)]:
                    got=buf[k][:state[j]].cpu().numpy();w=expected[k]
                    if k=='rhs':
                        np.testing.assert_array_equal(got[:,:2],w[:,:2]);got=got[:,4:];w=w[:,4:]
                    np.testing.assert_array_equal(got,w)
                results[name].append(ms)
        report[case]={k:{'ms':v,'median_ms':median(v)} for k,v in results.items()}
        (out/'timing.json').write_text(json.dumps(report,indent=1)+'\n')
        print(case,[(k,round(median(v),2)) for k,v in results.items()],flush=True)
        sessions.clear()
if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('reference','weights','out'):p.add_argument(k,type=Path)
    a=p.parse_args();measure(a.reference,a.weights,a.out)

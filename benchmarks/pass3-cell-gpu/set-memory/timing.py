"""Measure union-dependent Set maintenance on actual device state by paired amplification."""
import argparse
import json
from pathlib import Path
from statistics import median
import sys
from time import perf_counter_ns
import numpy as np
import torch

HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
from run import execute

@torch.inference_mode()
def measure(folder,weights,ports,out,cases):
    out.mkdir(parents=True,exist_ok=False);reports={}
    for case in cases:
        trial=folder/f'study-{case}';image=trial/'input/device.json'
        with np.load(trial/'gpu/output.npz') as z:
            expected={k:z[k] for k in ('rhs','writes','resumes','runs','rows','meta','parents','set_members')}
        steps=len(expected['runs'])+1
        sessions={};modes=[(1,False),(513,True),(513,False),(2049,True),(2049,False)]
        for repeats,control in modes:
            mode=f'{repeats}-{int(control)}'
            def retain(infer,buf,*unused):
                seeds={k:buf[k].clone() for k in ('state','meta','dyn','head','wm')}
                def reset():
                    for k,v in seeds.items():buf[k].copy_(v)
                    for k in ('regs','count','rhs','writes','runs','resumes'):buf[k].zero_()
                sessions[mode]=reset,infer,buf
            dest=out/f'{case}-{mode}'
            execute(image,weights,ports,steps,2,dest,maintenance_repeat=repeats,
                    maintenance_control=control,measure_resident=retain)
            tables=json.loads((trial/'input/ingress.json').read_text())['tables']
            with np.load(dest/'output.npz') as z:
                for k,want in expected.items():
                    if k=='rhs':
                        np.testing.assert_array_equal(z[k][:,:2],want[:,:2]);np.testing.assert_array_equal(z[k][:,4:],want[:,4:])
                    elif k=='rows':
                        for t,schema in enumerate(tables):
                            at=expected['meta'][:,0]==t;w=len(schema['schema'])
                            np.testing.assert_array_equal(z[k][at,:w],want[at,:w])
                    else:np.testing.assert_array_equal(z[k],want)
        modes=list(sessions)
        samples={m:[] for m in sessions};pairs={n:[] for n in (513,2049)}
        for i in range(10):
            order=modes[i%5:]+modes[:i%5]
            for mode in (order if i<5 else order[::-1]):
                reset,infer,buf=sessions[mode];reset();torch.mps.synchronize()
                start=perf_counter_ns();infer();torch.mps.synchronize();ms=(perf_counter_ns()-start)/1e6
                state=buf['state'].cpu().tolist()
                if state[5] or not state[7] or state[11]!=len(expected['runs']):raise ValueError((case,mode,state))
                for k,j in [('rhs',9),('writes',10),('resumes',16),('runs',11)]:
                    got=buf[k][:state[j]].cpu().numpy();want=expected[k]
                    if k=='rhs':
                        np.testing.assert_array_equal(got[:,:2],want[:,:2]);got=got[:,4:];want=want[:,4:]
                    np.testing.assert_array_equal(got,want)
                samples[mode].append(ms)
            for n in pairs:pairs[n].append(1000*(samples[f'{n}-0'][-1]-samples[f'{n}-1'][-1])/(n-1))
        base=median(samples['1-0'])
        reports[case]=dict(runs=steps-1,samples_ms=samples,resident_ms=base,maintenance_us={n:dict(
            median=median(v),q25=float(np.percentile(v,25)),q75=float(np.percentile(v,75)),samples=v,
            share_pct=median(v)/(10*base)) for n,v in pairs.items()})
        (out/'timing.json').write_text(json.dumps(reports,indent=1)+'\n')
        print(case,base,[(n,median(v)) for n,v in pairs.items()],flush=True)
        sessions.clear()
if __name__=='__main__':
    a=argparse.ArgumentParser()
    for k in ('studies','weights','ports','new_out'):a.add_argument(k,type=Path)
    a.add_argument('--cases',nargs='+',default=['full','full-probes','probes','union','dynamic'])
    p=a.parse_args();measure(p.studies,p.weights,p.ports,p.new_out,p.cases)

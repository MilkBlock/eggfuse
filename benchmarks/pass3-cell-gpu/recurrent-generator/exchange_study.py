"""Time identical trained policies and exact verification with different GPU dispatch boundaries."""
import argparse
import json
from pathlib import Path
from statistics import median
from time import perf_counter_ns

import numpy as np
import torch

from capture import execute, inputs, load_catalog, read, verify
from feedback_study import bind_session
from provenance import validate


def study(a):
    a.out.mkdir(parents=True,exist_ok=False)
    results={}
    for case in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax'):
        image,program,gold=inputs(a.corpus,a.ref,case)
        entries=load_catalog(image,program,a.ref/'sum-bits/program.json')
        for seed in (1703,1709):
            actor=read(a.capture/f'train-{seed}-2/actor.json')
            sessions,report={},{}
            for name,fusion in [('exact',None),('split',0),('exchange',1),('with-features',2)]:
                folder=a.out/f'{case}-{seed}-{name}'
                cfg=None if fusion is None else dict(catalog=entries,weights=actor['weights'],rows=2,hidden=8,
                                ranks=8,waves=2,feedback=2,receipt_head=True,fusion=fusion)
                execute(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,folder,
                        neural=cfg,measure_resident=bind_session(sessions,name))
                verify(folder,gold,image)
                report[name]=dict(ms=[],runs=read(folder/'run.json')['completed'],verified=True)
                if cfg:
                    report[name]['neural_committed']=validate(folder,entries)
                    with np.load(folder/'neural-output.npz') as z:
                        if fusion==0:
                            canonical={k:z[k].copy() for k in z.files}
                        else:
                            for k in canonical:np.testing.assert_array_equal(z[k],canonical[k],err_msg=f'{name} {k}')
            with np.load(gold/'output.npz') as z:truth={k:z[k] for k in ('runs','resumes','writes','rhs')}
            arms=list(sessions)
            for trial in range(2*len(arms)):
                order=arms[trial%len(arms):]+arms[:trial%len(arms)]
                for name in order if trial<len(arms) else order[::-1]:
                    reset,infer,buf=sessions[name]
                    reset();torch.mps.synchronize()
                    start=perf_counter_ns();infer();torch.mps.synchronize()
                    report[name]['ms'].append((perf_counter_ns()-start)/1e6)
                    st=buf['state'].cpu().tolist()
                    assert st[7] and not st[5]
                    for k,i in [('runs',11),('rhs',9),('writes',10),('resumes',16)]:
                        got,want=buf[k][:st[i]].cpu().numpy(),truth[k]
                        if k=='rhs':
                            np.testing.assert_array_equal(got[:,:2],want[:,:2]);got,want=got[:,4:],want[:,4:]
                        np.testing.assert_array_equal(got,want)
                    if name!='exact':
                        for k,field in [('raw_trace','raw'),('verdict','verdict')]:
                            np.testing.assert_array_equal(buf[k][:st[11]].cpu().numpy(),canonical[field])
            for arm in arms:report[arm]['median_ms']=median(report[arm]['ms'])
            print(case,seed,[(k,round(v['median_ms'])) for k,v in report.items()],flush=True)
            results[f'{case}/{seed}']=report
            (a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
            sessions.clear()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','reader','capture','out'):p.add_argument(k,type=Path)
    with torch.inference_mode():study(p.parse_args())

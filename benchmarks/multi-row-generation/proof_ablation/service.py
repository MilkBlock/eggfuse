"""Compare preissued certificates on exactly the same live short and long witnesses."""
import argparse
import json
from pathlib import Path
from statistics import median

import numpy as np
import torch

from bake import plans
from device_proof import compiled,issue,library
from measure import device,study


@torch.inference_mode()
def measure(root,out):
    dev=device();templates=study()[0];initial=plans();report={}
    for t in templates:
        name=t['id']
        if name not in ('rule-266','rule-143'):continue
        p=compiled(t,initial[name],dev)
        with np.load(root/'traces'/f'{name}-1703-all_requests.npz') as z:
            data={k:z[k] for k in ('a','b','parents','claims','requests','ctx')}
            ops=z['primitive_ranges'][...,1]-6
            valid=z['primitive_verdict'][...,0].astype(bool)
        for label,mask in [('one',ops==1),('long',ops>=4)]:
            eligible=np.argwhere(valid&mask)
            if not len(eligible):raise ValueError('empty length stratum')
            for batch in (1,128,4096):
                records=eligible[np.arange(batch)%len(eligible)]
                graphs,slots=records.T
                arrays=[v[graphs].copy() for v in data.values()]
                chosen=arrays[3][np.arange(batch),slots].copy()
                arrays[3][:]=0
                arrays[3][:,0]=chosen
                tensors=tuple(torch.as_tensor(v,device=dev) for v in arrays)
                buffers={}
                times={'primitive':[],'macro':[]}
                for macro in (False,True):
                    wire,ranges=issue(tensors,p,macro)
                    buffers[macro]=(wire,ranges,torch.empty_like(ranges))
                torch.mps.synchronize()
                for j in range(16):
                    for macro in ((False,True) if j%2 else (True,False)):
                        wire,ranges,verdict=buffers[macro]
                        start=torch.mps.Event(enable_timing=True);end=torch.mps.Event(enable_timing=True)
                        start.record()
                        library().verify(*tensors,p['cfg'],p['rules'],p['macro'],wire,ranges,verdict,int(macro),
                                         threads=batch*8,arg_casts={12:'int32'})
                        end.record();end.synchronize();ms=start.elapsed_time(end)
                        if j>=4:times['macro' if macro else 'primitive'].append(ms)
                for macro,(_,_,v) in buffers.items():
                    outcome=v.cpu().numpy()
                    assert (outcome[:,0,0]==1).all() and not outcome[:,1:,0].any()
                    np.testing.assert_array_equal(outcome[:,0,1],np.ones(batch) if macro else ops[graphs,slots])
                report[f'{name}/{label}/{batch}']=dict(distinct_available=len(eligible),samples_ms=times,
                                    median_us={k:median(v)*1000 for k,v in times.items()},
                                    mean_primitive_steps=float(ops[graphs,slots].mean()))
    out.write_text(json.dumps(report,indent=1)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();measure(a.root,a.output)

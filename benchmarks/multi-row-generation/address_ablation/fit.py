"""Train address heads with actual, differentiable GPU token handoff."""
import argparse
import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
import torch
from torch.nn import functional as F

from data import dataset
from model import AddressModel
from study import TRAIN, ARMS, SEEDS, digest, input_digest


def device():
    if os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK','0')!='0' or not torch.backends.mps.is_available():
        raise RuntimeError('MPS with CPU fallback disabled required')
    return torch.device('mps')


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('arm',choices=ARMS);p.add_argument('seed',type=int,choices=SEEDS);a=p.parse_args()
    dest=a.root/f'{a.arm}-{a.seed}';dest.mkdir(parents=True,exist_ok=True)
    if (dest/'final.pt').exists():raise FileExistsError(dest)
    torch.manual_seed(a.seed);dev=device()
    m=AddressModel(a.arm,width=48)
    initial=hashlib.sha256()
    for name,v in sorted(m.named_parameters()):
        initial.update(name.encode());initial.update(v.detach().numpy().tobytes())
    m.to(dev);m.train();opt=torch.optim.Adam(m.parameters(),lr=.002);rng=np.random.default_rng(a.seed)
    data=[dataset(*shape,512,91000+i) for i,shape in enumerate(TRAIN)]
    cols=('make_ref','finish_ref','value','target1','target2')
    coords_by_shape=[torch.as_tensor(d['coords'],device=dev) for d in data]
    history=[];batch_hash=hashlib.sha256();start=time.perf_counter()
    for step in range(1024):
        idx=step%len(TRAIN);_,length,ports=TRAIN[idx];coords=coords_by_shape[idx]
        sample=rng.integers(512,size=32)
        batch_hash.update(sample.tobytes())
        mq,fq,val,t1,t2=[torch.as_tensor(data[idx][k][sample],device=dev) for k in cols]
        opt.zero_grad(set_to_none=True)
        out=m(coords,mq,fq,val,length,ports)
        loss=F.cross_entropy(out['scores1'].flatten(0,1),t1.long().flatten())+F.cross_entropy(out['scores2'].flatten(0,1),t2.long().flatten())
        loss.backward();opt.step()
        if step%256==0 or step==1023:
            x=float(loss.detach())
            if not np.isfinite(x):raise ValueError('nonfinite fit')
            history.append(dict(step=step+1,loss=x,seconds=time.perf_counter()-start))
            print(history[-1],flush=True)
    torch.save(m.state_dict(),dest/'final.pt')
    report=dict(arm=a.arm, seed=a.seed, steps=1024, batch=32, init=initial.hexdigest(),
                data_order=batch_hash.hexdigest(),train_hashes=[input_digest(d) for d in data],
                params=sum(v.numel() for v in m.parameters()),weight=digest(dest/'final.pt'),history=history)
    (dest/'fit.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__': main()

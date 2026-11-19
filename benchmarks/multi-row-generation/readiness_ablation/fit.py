"""Supervise proposals offline, unrolling only observed event waves."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter
import numpy as np
import torch
from torch.nn import functional as F

from data import dataset
from predictor import ReadyPolicy

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def device():
    if not torch.backends.mps.is_available() or os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK','0')!='0':
        raise RuntimeError('MPS with CPU fallback disabled required')
    return torch.device('mps')

def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('arm',choices=('keyed','blind'));p.add_argument('seed',type=int,choices=(1703,1709));a=p.parse_args()
    dev=device();folder=a.root/f'{a.arm}-{a.seed}';folder.mkdir(parents=True,exist_ok=True)
    if (folder/'final.pt').exists():raise FileExistsError(folder)
    torch.manual_seed(a.seed);m=ReadyPolicy(a.arm)
    init=hashlib.sha256(b''.join(v.detach().numpy().tobytes() for v in m.parameters())).hexdigest();m=m.to(dev)
    opt=torch.optim.Adam(m.parameters(),lr=.002);d=dataset('train');rng=np.random.default_rng(a.seed)
    batches=hashlib.sha256();history=[];start=perf_counter()
    for step in range(768):
        ix=rng.integers(len(d['events']),size=32);batches.update(ix.tobytes())
        stream=m.new_stream();opt.zero_grad(set_to_none=True)
        pred=torch.stack([stream.scores(i,torch.as_tensor(d['events'][ix,i],device=dev) if i<3 else None) for i in range(4)],1)
        y=torch.as_tensor(d['desired_ready'][ix],device=dev).to(pred.dtype)
        loss=F.binary_cross_entropy_with_logits(pred,y);loss.backward();opt.step()
        if step%192==0 or step==767:
            item=dict(step=step+1,loss=loss.detach().item(),seconds=perf_counter()-start)
            if not np.isfinite(item['loss']):raise ValueError(item)
            print(item,flush=True);history.append(item)
    torch.save(m.state_dict(),folder/'final.pt')
    (folder/'fit.json').write_text(json.dumps(dict(arm=a.arm,seed=a.seed,init=init,params=sum(w.numel() for w in m.parameters()),
              batch_sha256=batches.hexdigest(),train_input_sha256=hashlib.sha256(d['events'].tobytes()).hexdigest(),
              weight_sha256=digest(folder/'final.pt'),history=history),indent=2)+'\n')

if __name__=='__main__':main()

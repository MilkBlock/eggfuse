"""Fit work/wait/close on exact device trajectories from training templates."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from torch.nn import functional as F

from queue_gpu import Gate,Queue,dataset,study,device,load_producer,upload,device_plan,inputs,MAX_TICKS,digest


def train(root,producers,seed):
    dev=device();_,train,_,schema=study()
    p=load_producer(schema,seed,producers,dev);rows=[]
    for t in train:
        d=dataset('train',t);x=upload(d,slice(None),dev)
        table=p.encoder.encode_bank(schema.bank(t,'pairwise',dev));plan=device_plan(t['id'],dev)
        _,args=inputs(p,x,table,plan,'train',torch.arange(len(x[0]),device=dev))
        queue=Queue(len(x[0]),plan[3],dev,True)
        # Fixed slices hold a genuinely quiescent state long enough to supply
        # positive stop labels; early-closing exact trajectories alone omit it.
        queue.advance(args,torch.zeros(123,device=dev),'fixed',4,MAX_TICKS)
        z=queue.trace.cpu().numpy().reshape(-1,11);rows.append(z[z[:,6]>=0,:7])
    samples=np.concatenate(rows);xs=torch.tensor(samples[:,:6]/3,device=dev,dtype=torch.float32)
    ys=torch.tensor(samples[:,6],device=dev,dtype=torch.long)
    root.mkdir(parents=True,exist_ok=True)
    for blind in (False,True):
        name=f'{"blind" if blind else "ledger"}-{seed}';file=root/(name+'.pt')
        if file.exists():raise FileExistsError(file)
        torch.manual_seed(seed);m=Gate().to(dev);opt=torch.optim.Adam(m.parameters(),lr=.009)
        rng=np.random.default_rng(seed);batch_hash=hashlib.sha256();features=xs.clone()
        if blind:features[:,4:]=0
        for step in range(512):
            ix=rng.integers(len(samples),size=128);batch_hash.update(ix.tobytes())
            opt.zero_grad(set_to_none=True);loss=F.cross_entropy(m(features[ix]),ys[ix])
            loss.backward();opt.step()
        torch.save(m.state_dict(),file)
        file.with_suffix('.json').write_text(json.dumps(dict(seed=seed,blind=blind,params=123,steps=512,
            batch_hash=batch_hash.hexdigest(),trace_hash=hashlib.sha256(samples.tobytes()).hexdigest(),
            examples=len(samples),labels=np.bincount(samples[:,6]).tolist(),final_loss=loss.item(),weight=digest(file))))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('root',type=Path);p.add_argument('producers',type=Path);p.add_argument('seed',type=int)
    a=p.parse_args();train(a.root,a.producers,a.seed)

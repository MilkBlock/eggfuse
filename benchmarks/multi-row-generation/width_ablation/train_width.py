"""Fit one row once per seed. Width is never changed during training."""
import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import torch
from model import WidthSystem
from study import dataset,templates,SEEDS,array_digest
from fit import objective,align,device,transfer,EClassSchema,state_digest,digest

def main():
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('seed',type=int,choices=SEEDS);args=parser.parse_args()
    folder=args.root/str(args.seed);folder.mkdir(parents=True,exist_ok=True)
    if (folder/'final.pt').exists():raise FileExistsError(folder)
    dev=device();ts=[t for t in templates() if t['split']=='train'];schema=EClassSchema(ts)
    panels={t['id']:dataset('train',t) for t in ts}
    banks={t['id']:schema.bank(t,'pairwise',dev) for t in ts}
    model=WidthSystem(schema,args.seed)
    assert not any(k.endswith(('position.weight','source_position.weight')) for k,_ in model.decoder.named_parameters())
    initial=state_digest(model.state_dict());model.to(dev);model.train()
    optimizer=torch.optim.Adam(model.parameters(),lr=.001);rng=np.random.default_rng(args.seed)
    order=[];history=[];start=time.perf_counter();trace=hashlib.sha256()
    for step in range(1536):
        if not order:order=list(rng.permutation(len(ts)))
        t=ts[order.pop()];d=panels[t['id']];ix=rng.integers(len(d['a']),size=32)
        trace.update(t['id'].encode());trace.update(ix.tobytes())
        optimizer.zero_grad(set_to_none=True);table=model.encoder.encode_bank(banks[t['id']])
        stages,token,relations=model(*transfer(d,ix,dev),table,rows=1)
        labels=align(stages,d['target1'][ix],d['target2'][ix])
        loss=objective(model,stages,relations,[torch.as_tensor(y,device=dev,dtype=torch.long) for y in labels],
                       torch.as_tensor(d['request_legal'][ix],device=dev,dtype=torch.long))
        loss.backward();optimizer.step()
        if step%384==0 or step==1535:
            sample=dict(step=step+1,loss=float(loss.detach()),seconds=time.perf_counter()-start)
            if not np.isfinite(sample['loss']):raise ValueError('nonfinite training')
            history.append(sample);print(sample,flush=True)
    torch.save(model.state_dict(),folder/'final.pt')
    result=dict(initial=initial,seed=args.seed,arm='single-row pairwise',steps=1536,history=history,lr=.001,
                model_sha256=digest(folder/'final.pt'),data_order=trace.hexdigest(),params=sum(p.numel() for p in model.parameters()),
                source={t['id']:array_digest(panels[t['id']]) for t in ts},torch=torch.__version__)
    (folder/'fit.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()

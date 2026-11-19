"""Supervise a shared pair-utility head on seven source template families' members."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import torch
from torch.nn import functional as F

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'locality_ablation'))
from experiment import dataset, study, device, load_producer, produce, upload, digest
from actor import PairActor,projected_utility


def train(root,producers,seed):
    dev=device();_,templates,_,schema=study()
    producer=load_producer(schema,seed,producers,dev)
    torch.manual_seed(seed)
    model=PairActor().to(dev)
    optimizer=torch.optim.Adam(model.parameters(),lr=.003)
    banks=[]
    for t in templates:
        batch=dataset('train',t)
        x=upload(batch,slice(None),dev)
        table=producer.encoder.encode_bank(schema.bank(t,'pairwise',dev))
        _,token=produce(producer,x,table)
        banks.append((token,x[2],projected_utility(token,x[2],model.pairs)))
    rng=np.random.default_rng(seed);order=hashlib.sha256()
    for step in range(768):
        tokens,requests,utility=banks[step%len(banks)]
        ix=rng.integers(len(tokens),size=48);order.update(ix.tobytes())
        optimizer.zero_grad(set_to_none=True)
        loss=F.mse_loss(model(tokens[ix],requests[ix]),utility[ix])
        loss.backward();optimizer.step()
    if not torch.isfinite(loss).item():raise ValueError('non-finite actor')
    root.mkdir(parents=True,exist_ok=True)
    path=root/f'actor-{seed}.pt'
    if path.exists():raise FileExistsError(path)
    torch.save(model.state_dict(),path)
    path.with_suffix('.json').write_text(json.dumps(dict(seed=seed,steps=768,params=sum(p.numel() for p in model.parameters()),
        last_loss=loss.item(),weight=digest(path),batch_sha256=order.hexdigest(),templates=[t['id'] for t in templates])))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('root',type=Path);p.add_argument('producers',type=Path);p.add_argument('seed',type=int)
    args=p.parse_args();train(args.root,args.producers,args.seed)

"""Train paired coordination policies, then run both complete GPU stages."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import torch
from torch.nn import functional as F

from network import Coordinator, device, digest, load_producer, produce, study, transfer
from data import dataset


def static(template, dev):
    cert, = template['certificates']
    return torch.tensor([cert['left_port'],cert['right_port']],device=dev)


def upload(d,ix,dev):
    return transfer(d,ix,dev)


def cpu(stage):
    return {k:stage[k].detach().cpu().numpy() for k in ('active','pointers','rows')}


def fit(args):
    dev=device()
    _,train,_,schema=study()
    p=load_producer(schema,args.seed,args.producers,dev)
    torch.manual_seed(args.seed)
    m=Coordinator()
    initial=hashlib.sha256(b''.join(v.detach().numpy().tobytes() for v in m.parameters())).hexdigest()
    m=m.to(dev)
    opt=torch.optim.Adam(m.parameters(),lr=.003)
    inputs={}
    for t in train:
        d=dataset('train',t)
        table=p.encoder.encode_bank(schema.bank(t,'pairwise',dev))
        x=upload(d,slice(None),dev)
        with torch.no_grad():
            _,token=produce(p,x,table)
        inputs[t['id']]=(token,(x[2],*x[4:]),static(t,dev),torch.tensor(d['request_legal'],device=dev).float())
    rng=np.random.default_rng(args.seed)
    batches=hashlib.sha256()
    for step in range(1024):
        t=train[step % len(train)]
        ix=rng.integers(len(inputs[t['id']][0]),size=48)
        batches.update(t['id'].encode());batches.update(ix.tobytes())
        token,controls,ports,target=inputs[t['id']]
        opt.zero_grad(set_to_none=True)
        _,logits,_,_=m(token[ix],tuple(v[ix] for v in controls),ports,args.scope)
        loss=F.binary_cross_entropy_with_logits(logits,target[ix])
        loss.backward();opt.step()
    if not torch.isfinite(loss).item():raise ValueError('nonfinite training')
    args.root.mkdir(parents=True,exist_ok=True)
    out=args.root/f'{args.scope}-{args.seed}.pt'
    if out.exists():raise FileExistsError(out)
    torch.save(m.state_dict(),out)
    out.with_suffix('.json').write_text(json.dumps(dict(initial=initial,batches=batches.hexdigest(),
        weight=digest(out),params=sum(v.numel() for v in m.parameters()),final_loss=loss.item())))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('root',type=Path)
    parser.add_argument('producers',type=Path)
    parser.add_argument('seed',type=int,choices=(1703,1709))
    parser.add_argument('scope',choices=('global','local'))
    fit(parser.parse_args())

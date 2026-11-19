"""Fit four matched encoders on frozen certified template families."""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from model import AliasSystem, BASE, INPUTS
from encoder import EClassSchema, ARMS
from learning import align, per_slot, state_digest

SEEDS=(1703,1709)
MANIFEST=BASE/'corpus/manifest.json'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def study():
    templates=json.loads(MANIFEST.read_text())['templates']
    train=[t for t in templates if t['split']=='train']
    test=[t for t in templates if t['split']=='heldout']
    if not test or {t['family_id'] for t in train}&{t['family_id'] for t in test}:
        raise ValueError('need strict family holdout')
    return templates,train,test,EClassSchema(train)


def device():
    if not torch.backends.mps.is_available() or os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK','0')!='0':
        raise RuntimeError('MPS with fallback disabled required')
    return torch.device('mps')


def transfer(data,ix,dev):
    return tuple(torch.as_tensor(data[key][ix],device=dev,dtype=torch.int32) for key in INPUTS)


def objective(model,stages,relations,targets,semantic):
    val=F.cross_entropy(relations.flatten(0,1),semantic.flatten())
    for s,y,head in zip(stages,targets,model.aux):
        live=y[...,0]
        val=val+per_slot(s['active_logits'],live).mean()
        for j,name in enumerate(('left_logits','right_logits'),1):
            val=val+(live*per_slot(s[name],y[...,j])).mean()
        predicted=head(s['hidden']).unflatten(-1,(5,8))
        aux=F.cross_entropy(predicted.flatten(0,2),y[...,3:].flatten(),reduction='none')
        val=val+(live*aux.reshape(*live.shape,5).mean(-1)).mean()
    return val


def main():
    from data import dataset
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);p.add_argument('arm',choices=ARMS);p.add_argument('seed',type=int,choices=SEEDS);args=p.parse_args()
    dev=device();_,train,_,schema=study()
    folder=args.out/f'{args.arm}-{args.seed}';folder.mkdir(parents=True,exist_ok=True)
    if (folder/'final.pt').exists():raise FileExistsError(folder)
    panels={t['id']:dataset('train',t) for t in train}
    banks={t['id']:schema.bank(t,args.arm,dev) for t in train}
    model=AliasSystem(schema,args.seed)
    initial=state_digest(model.state_dict())
    model.to(dev);optimizer=torch.optim.Adam(model.parameters(),lr=.001);rng=np.random.default_rng(args.seed)
    order=[];history=[];start=time.perf_counter();trace=hashlib.sha256()
    for step in range(1536):
        if not order:order=list(rng.permutation(len(train)))
        t=train[order.pop()];d=panels[t['id']];ix=rng.integers(len(d['a']),size=32)
        trace.update(t['id'].encode());trace.update(ix.tobytes())
        inputs=transfer(d,ix,dev)
        optimizer.zero_grad(set_to_none=True)
        table=model.encoder.encode_bank(banks[t['id']])
        stages,token,semantic=model(*inputs,table)
        labels=align(stages,d['target1'][ix],d['target2'][ix])
        loss=objective(model,stages,semantic,[torch.as_tensor(y,device=dev,dtype=torch.long) for y in labels],
                       torch.as_tensor(d['request_legal'][ix],device=dev,dtype=torch.long))
        loss.backward();optimizer.step()
        if step%384==0 or step==1535:
            r=dict(step=step+1,loss=float(loss.detach()),seconds=time.perf_counter()-start)
            if not np.isfinite(r['loss']):raise ValueError('nonfinite fit')
            history.append(r);print(r,flush=True)
    torch.save(model.state_dict(),folder/'final.pt')
    result=dict(arm=args.arm,seed=args.seed,steps=1536,batch=32,history=history,initial_sha256=initial,
                num_parameters=sum(w.numel() for w in model.parameters()),weight_sha256=digest(folder/'final.pt'),
                data_order_sha256=trace.hexdigest(),corpus_sha256=digest(MANIFEST),torch=torch.__version__,
                train_input_sha256={t['id']:hashlib.sha256(b''.join(panels[t['id']][k].tobytes()
                    for k in INPUTS+('target1','target2','request_legal'))).hexdigest() for t in train})
    (folder/'fit.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()

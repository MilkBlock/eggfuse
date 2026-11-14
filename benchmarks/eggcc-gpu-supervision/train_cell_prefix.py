"""Fit next-Entry choices using current context, not recurrent latents.

Standalone training-domain experiment; does not replace runtime enumeration.
"""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
from cell_prefix_targets import build
from cell_context_features import port_context


def features(data,contexts):
    lookup={};requests={};atoms=data['entry_records'].shape[1];ports=data['entry_roots'].shape[2]
    for i in range(len(data['valid'])):
        c=int(data['case'][i]);r=int(data['rule'][i]);requests[c,r]=data['request'][i]
        for d,record in enumerate(data['entry_records'][i]):
            if record<0:continue
            key=c,r,d,int(data['entry_sources'][i,d]),int(record)
            value=data['entry_roots'][i,d]
            if key in lookup and not np.array_equal(value,lookup[key]):raise ValueError('ambiguous Entry projection')
            lookup[key]=value
    rows=build(data);xx=[];yy=[];groups=[]
    for group,row in enumerate(rows):
        c,r=row['case'],row['rule'];depth=len(row['prefix']);bank=contexts[c]
        previous=np.full((atoms,ports),-1,np.int32)
        for d,(source,record) in enumerate(row['prefix']):previous[d]=lookup[c,r,d,source,record]
        pc=port_context(bank,previous).reshape(-1)
        for source,record in row['offered']:
            roots=lookup[c,r,depth,source,record]
            links=(roots[None,:,None]==previous[:,None,:])&(roots[None,:,None]>=0)&(previous[:,None,:]>=0)
            x=np.concatenate([requests[c,r],np.eye(atoms,dtype=np.float32)[depth],
                              port_context(bank,roots).reshape(-1),pc,links.astype(np.float32).reshape(-1)])
            xx.append(x);yy.append((source,record) in row['legal_next']);groups.append(group)
    return np.array(xx,np.float32),np.array(yy,np.float32),np.array(groups),len(rows)


def main():
    p=argparse.ArgumentParser();p.add_argument('dataset',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--steps',type=int,default=2000);a=p.parse_args()
    if a.steps<1:raise ValueError('positive training steps required')
    manifest=json.loads(a.dataset.with_suffix('.json').read_text());digest=hashlib.sha256(a.dataset.read_bytes()).hexdigest()
    if manifest['dataset_sha256']!=digest:raise ValueError('dataset hash mismatch')
    meta=manifest['context_bank'];path=a.dataset.parent/meta['file']
    if hashlib.sha256(path.read_bytes()).hexdigest()!=meta['sha256']:raise ValueError('context hash mismatch')
    data=dict(np.load(a.dataset,allow_pickle=False));bank=dict(np.load(path,allow_pickle=False))
    contexts=[{k:bank[f'case_{i}_{k}'] for k in ('roots','roles','mask','slot_valid')} for i in range(meta['cases'])]
    x,y,groups,count=features(data,contexts);seen={};conflicts=0
    for v,t in zip(x,y):
        key=v.tobytes()
        if key in seen and seen[key]!=t:conflicts+=1
        else:seen[key]=t
    mx.random.seed(2027);model=nn.Sequential(nn.Linear(x.shape[1],128),nn.GELU(),nn.Linear(128,128),nn.GELU(),nn.Linear(128,1))
    dx,dy=mx.array(x),mx.array(y)
    def loss(m,xx,yy):return nn.losses.binary_cross_entropy(m(xx)[:,0],yy,reduction='mean')
    grad=nn.value_and_grad(model,loss);opt=optim.Adam(learning_rate=3e-4);rng=np.random.default_rng(2027)
    for step in range(a.steps):
        ids=mx.array(rng.integers(len(y),size=128));value,g=grad(model,dx[ids],dy[ids]);opt.update(model,g);mx.eval(value,model.parameters(),opt.state)
        if step%500==0:print(json.dumps(dict(step=step,loss=float(value))),flush=True)
    scores=model(dx)[:,0];mx.eval(scores);pred=np.array(scores)>=0;truth=y>0
    result=dict(scope='synthetic training-domain next-Entry classification; no runtime candidate reduction',
                examples=len(y),prefix_states=count,input_width=x.shape[1],steps=a.steps,
                correct_prefix_states=sum(bool(np.all(pred[groups==i]==truth[groups==i])) for i in range(count)),
                false_positive=int(np.sum(pred&~truth)),false_negative=int(np.sum(~pred&truth)),
                exact_feature_label_conflicts=conflicts,dataset_sha256=digest,context_sha256=meta['sha256'],
                recurrent_latent_inputs=False,numeric_identity_inputs=False,promoted_as_default=False)
    model.save_weights(str(a.output.with_suffix('.safetensors')));a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()

"""Offline matching supervises predictions. Neither generated stage reads labels."""
import argparse
import hashlib
import json
import time
from pathlib import Path
import sys
import numpy as np
import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
from cross_model import BASE, CrossRun, projection_recipe
from assignment import assign
sys.path.insert(0,str(BASE/'data'))
from crossrun_data import dataset


def hashfile(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def assignment(output, target):
    # Match on activation and correlated parent choices. All arms see the same loss definition.
    active = target[...,0]
    score = np.zeros((len(active),8,8))
    for col, logits in enumerate(output[:3]):
        values = np.asarray(logits)
        maximum = values.max(-1, keepdims=True)
        nll = maximum + np.log(np.exp(values-maximum).sum(-1,keepdims=True))-values
        chosen = np.take_along_axis(nll[:,:,None,:],target[:,None,:,col,None],-1)[...,0]
        score += chosen if col==0 else chosen*active[:,None,:]
    return assign(score)


def training_labels(first, second, requests, y1, y2):
    batch = np.arange(len(y1))[:,None]
    first_slots = assignment(first,y1)
    t1 = y1[batch,first_slots]
    t2 = y2.copy()
    # Source semantics name parents by (i,j). Resolve supervision into the producer's
    # actual output layout using the training assignment, never insert it into Pair tokens.
    match = (t2[:,:,None,1:3]==t1[:,None,:,1:3]).all(-1)&(t1[:,None,:,0]!=0)
    req = (t2[:,:,None,1:3]==requests[:,None,:,:2]).all(-1)
    live = t2[...,0]!=0
    if not (match.sum(-1)[live]==1).all() or not (req.sum(-1)[live]==1).all():
        raise ValueError('target has no unique producer or request')
    t2[...,1] = match.argmax(-1)
    t2[...,2] = req.argmax(-1)
    return t1,t2[batch,assignment(second,t2)]


def loss(model,a,b,requests,t1,t2):
    out,_ = model(a,b,requests,training_heads=True)
    total = mx.array(0.)
    for (active,left,right,fields),target in zip(out,(t1,t2)):
        live = target[...,0]
        total += nn.losses.cross_entropy(active,live,reduction='mean')
        for col, scores in enumerate((left,right),1):
            total += mx.mean(live*nn.losses.cross_entropy(scores,target[...,col]))
        if model.arm != 'static':
            for col, (lo,hi) in enumerate(((0,8),(8,12),(12,16)),3):
                total += mx.mean(live*nn.losses.cross_entropy(fields[...,lo:hi],target[...,col]))
    return total


def main():
    p=argparse.ArgumentParser(); p.add_argument('directory',type=Path);p.add_argument('arm',choices=['learned','static','aux']);p.add_argument('seed',type=int);args=p.parse_args()
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu)
    out=args.directory/f'{args.arm}-{args.seed}';out.mkdir(parents=True,exist_ok=True)
    if (out/'model.safetensors').exists():raise FileExistsError(out)
    parent=args.directory.parent/'multi-row-streaming-20261118'/f'feedback-{args.seed}'
    checkpoint=parent/'model.safetensors';assert hashfile(checkpoint)==json.loads((parent/'result.json').read_text())['model_sha256']
    path=BASE/'compiler/plan.json';mx.random.seed(args.seed)
    m=CrossRun(args.arm,projection_recipe(path));m.make.load_weights(str(checkpoint));mx.eval(m.parameters())
    m.save_weights(str(out/'initial.safetensors'));initial=hashfile(out/'initial.safetensors')
    opt=optim.Adam(learning_rate=.0003);grad=nn.value_and_grad(m,loss);rng=np.random.default_rng(args.seed)
    training=dataset('train'); history=[];start=time.perf_counter()
    def get_scores(a,b,req):
        preds,_=m(a,b,req)
        return [v[:3] for v in preds]
    get_scores=mx.compile(get_scores,inputs=m.state)
    state=[m.state,opt.state]
    def step(a,b,req,y1,y2):
        val,gs=grad(m,a,b,req,y1,y2);opt.update(m,gs);return val
    step=mx.compile(step,inputs=state,outputs=state)
    for i in range(2000):
        ix=rng.integers(len(training['a']),size=32)
        a,b,req=(mx.array(training[k][ix]) for k in ('a','b','requests'))
        first,second=get_scores(a,b,req);mx.eval(first,second)
        t1,t2=training_labels(first,second,training['requests'][ix],training['target1'][ix],training['target2'][ix])
        val=step(a,b,req,mx.array(t1),mx.array(t2));mx.eval(val,state)
        if i%500==0 or i==1999:
            history.append(dict(step=i+1,loss=float(val),seconds=time.perf_counter()-start));print(history[-1],flush=True)
    if not np.isfinite(history[-1]['loss']):raise ValueError('nonfinite fit')
    m.save_weights(str(out/'model.safetensors'))
    meta=dict(arm=args.arm,seed=args.seed,steps=2000,history=history,parent_sha256=hashfile(checkpoint),plan_sha256=hashfile(path),initial_sha256=initial,model_sha256=hashfile(out/'model.safetensors'),training_input_sha256=hashlib.sha256(b''.join(training[k].tobytes() for k in ('a','b','requests','target1','target2'))).hexdigest())
    (out/'fit.json').write_text(json.dumps(meta,indent=2)+'\n')

if __name__=='__main__':main()

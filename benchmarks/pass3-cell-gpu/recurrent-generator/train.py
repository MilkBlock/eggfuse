"""Train from real source windows. The recurrent input always comes from the actor."""
import argparse,json
from pathlib import Path
import numpy as np
import torch
from model import Actor,set_loss,HIDDEN,ROWS,LEAVES,RANKS

def train(capture,dest,seed,updates=480):
    torch.set_num_threads(1);torch.manual_seed(seed);rng=np.random.default_rng(seed)
    summary=json.loads((capture/'summary.json').read_text())
    names=[n for n,v in summary.items() if v['split']=='train'];assert len(names)==4
    ds=[]
    for n in names:
        with np.load(capture/n/'training.npz') as z:
            x=torch.tensor(z['features']);y=torch.tensor(z['positive'])
            ds.append((x,y,np.flatnonzero(z['positive'].any(1))))
    model=Actor();opt=torch.optim.Adam(model.parameters(),lr=.007)
    losses=[]
    for step in range(updates):
        obs=[];labels=[]
        for j in range(12):
            x,y,positive=ds[int(rng.integers(len(ds)))]
            end=int(rng.choice(positive)) if j%2==0 else int(rng.integers(11,len(x)))
            start=max(0,end-11)
            obs.append(x[start:start+12]);labels.append(y[start:start+12])
        obs=torch.stack(obs);labels=torch.stack(labels)
        previous=torch.zeros(len(obs),ROWS,HIDDEN+4);loss=0
        for t in range(obs.shape[1]):
            logits,previous=model.step(obs[:,t],previous)
            loss+=set_loss(logits,labels[:,t])
        loss=loss/obs.shape[1];opt.zero_grad();loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(),1.0);opt.step()
        if step%40==0:losses.append(float(loss.detach()))
    dest.mkdir(parents=True,exist_ok=False)
    torch.save(model.state_dict(),dest/'actor.pt')
    (dest/'actor.json').write_text(json.dumps(dict(schema='eggfuse.recurrent-leaf/v1',seed=seed,train=names,updates=updates,
        rows=ROWS,ranks=RANKS,leaves=LEAVES,hidden=HIDDEN,params=sum(p.numel() for p in model.parameters()),
        weights=model.metal_weights(),loss_every_40=losses),separators=(',',':'))+'\n')
    print(seed,losses,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('capture',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--seed',type=int,required=True);p.add_argument('--updates',type=int,default=480)
    a=p.parse_args();train(a.capture,a.output,a.seed,a.updates)

"""Train the causal source-row gate on four disjoint native Pass 3 programs. Calibrate only on training."""
import argparse,json
from pathlib import Path
import numpy as np
import torch
from torch import nn

CASES=['affine-twins','clamped-ramp','segmented-prefix','window-laplacian']
class Net(nn.Module):
    def __init__(self,certified=False):
        super().__init__();self.x=nn.Linear(14,8);self.h=nn.Linear(4,8,bias=False);self.read=nn.Linear(8,1)
        self.rules=nn.Embedding(64,1);self.recurrent=nn.Linear(4,4);self.update=nn.Linear(4,4,bias=False)
        nn.init.zeros_(self.rules.weight);self.certified=certified
        self.mask=torch.ones(14)
        if certified:self.mask[[6,7,8,10,11,12]]=0
    def context_weight(self):return .03*self.h.weight.tanh() if self.certified else self.h.weight
    def features(self,x,rid,state):
        return self.read((self.x(x*self.mask)+nn.functional.linear(state,self.context_weight())[:,None]).tanh()).squeeze(-1)+self.rules(rid%64).squeeze(-1)[:,None]
    def advance(self,x,rid,state,n,counts,emit):
        sums=torch.stack([n.clamp_max(128)/128,(counts*emit).sum(1)/n,(counts*x[:,:,5]).sum(1)/n,(rid%64)/63],1)
        return (self.recurrent(state)+self.update(sums)).tanh()
def dataset(p):
    d=json.loads(p.read_text())['single_witness'];features=torch.tensor(d['features'],dtype=torch.float32)/32
    sequence=[]
    for r,n,b in d['events']:
        ids=[v[0] for v in b];y=torch.tensor([v[1] for v in b],dtype=torch.float32)
        sequence.append((r,float(n),features[ids],y))
    return sequence
def tensor(events):
    maxn=max(len(x) for _,_,x,_ in events);bs=len(events)
    x=torch.zeros(bs,maxn,14);c=torch.zeros(bs,maxn,2)
    for i,(_,_,f,y) in enumerate(events):x[i,:len(f)]=f;c[i,:len(f)]=y
    return x,torch.tensor([b[0] for b in events]),torch.tensor([b[1] for b in events]),c
@torch.inference_mode()
def min_positive(model,seq,threshold):
    h=torch.zeros(1,4);minimum=float('inf');total=selected=ok=0
    for event in seq:
        x,r,n,c=tensor([event]);count=c.sum(-1);s=model.features(x,r,h);emit=(s>=threshold).float()
        if (c[:,:,1]>0).any():minimum=min(minimum,float(s[c[:,:,1]>0].min()))
        total+=int(count.sum());selected+=int((count*emit).sum());ok+=int((c[:,:,1]*emit).sum())
        h=model.advance(x,r,h,n,count,emit)
    return minimum,total,selected,ok
def fit(a):
    torch.set_num_threads(1);torch.manual_seed(a.seed);rng=np.random.default_rng(a.seed);m=Net(a.certified)
    data=[dataset(a.data/c/'report.json') for c in CASES]
    opt=torch.optim.Adam(m.parameters(),lr=.012)
    for step in range(360):
        windows=[]
        for _ in range(10):
            seq=data[int(rng.integers(4))];t=int(rng.integers(len(seq)-9));windows.append(seq[t:t+8])
        h=torch.zeros(10,4);loss=0.
        for tick in range(8):
            x,r,n,c=tensor([w[tick] for w in windows]);count=c.sum(-1)
            s=m.features(x,r,h);pos=c[:,:,1];neg=c[:,:,0]
            loss+=((nn.functional.softplus(-s)*pos*16+nn.functional.softplus(s)*neg).sum(1)/(n+15*pos.sum(1))).mean()
            soft=s.sigmoid();emit=(s>=0).float()+(soft-soft.detach());h=m.advance(x,r,h,n,count,emit)
        opt.zero_grad();(loss/8).backward();nn.utils.clip_grad_norm_(m.parameters(),1.);opt.step()
    threshold=0.
    for _ in range(5):
        stats=[min_positive(m,d,threshold) for d in data];v=min(s[0] for s in stats)
        if v>=threshold:break
        threshold=float(np.floor(2*v)/2-.75)
    result=dict(certified_inputs=a.certified,threshold=threshold,x=(m.x.weight*m.mask).tolist(),b=m.x.bias.tolist(),h=m.context_weight().tolist(),
                out=m.read.weight[0].tolist(),bias=m.read.bias.item(),rules=m.rules.weight[:,0].tolist(),
                recurrent=m.recurrent.weight.tolist(),rbias=m.recurrent.bias.tolist(),update=m.update.weight.tolist())
    a.out.mkdir(parents=True,exist_ok=False)
    (a.out/'config.json').write_text(json.dumps(dict(mode='learned',residual=True,model=result),separators=(',',':')))
    (a.out/'training.json').write_text(json.dumps(dict(seed=a.seed,programs=CASES,updates=360,threshold=threshold,
       params=sum(p.numel() for p in m.parameters()),train_stats=[min_positive(m,d,threshold) for d in data]),indent=1)+'\n')
    print(a.seed,threshold,[(s[1],s[2],s[3]) for s in stats],flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('data',type=Path);p.add_argument('out',type=Path);p.add_argument('--seed',type=int,default=1703)
    p.add_argument('--certified',action='store_true');fit(p.parse_args())

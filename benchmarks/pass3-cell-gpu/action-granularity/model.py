"""One recurrent row chooses one root address and a single library unit; auxiliary head predicts raw witness rank."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np
import torch
from torch import nn

GEN=Path(__file__).resolve().parents[1]/'recurrent-generator'
spec=importlib.util.spec_from_file_location('leaf_model',GEN/'model.py');leaf=importlib.util.module_from_spec(spec);spec.loader.exec_module(leaf)
H,R,ROWS=leaf.HIDDEN,leaf.RANKS,leaf.ROWS


def read(p):
    return json.loads(p.read_bytes())


def joins_for(program):
    return [[i+32,j['left'],j['output'],j['right']] for i,j in enumerate(program['iterative_bake']['joins'])
            if j['left']<32 and j['right']<32]


class Actor(nn.Module):
    def __init__(self,joins):
        super().__init__();self.root=leaf.Actor()
        self.register_buffer('joins',torch.tensor(joins),persistent=False)
        self.unit_weights=nn.Parameter(torch.randn(len(joins),H)*.08)
        self.unit_bias=nn.Parameter(torch.zeros(len(joins)))
        self.unit_row=nn.Parameter(torch.zeros(ROWS,len(joins)))
        self.unit_embed=nn.Parameter(torch.randn(len(joins),H)*.05)
        self.stop=nn.Parameter(torch.zeros(ROWS))
        self.rank_weights=nn.Parameter(torch.randn(R,H)*.05)
        self.rank_bias=nn.Parameter(torch.zeros(32,R,R))

    def step(self,x,prev):
        root_logits,token=self.root.step(x,prev)
        hidden=token[:,:,:H];left=token[:,:,H].long()-1;rank=token[:,:,H+2].long()-1
        score=hidden@self.unit_weights.T+self.unit_bias+self.unit_row
        score=score.masked_fill(left[:,:,None]!=self.joins[:,1],-1e4)
        logits=torch.cat([self.stop[None,:,None].expand(len(x),-1,-1),score],-1)
        choice=logits.argmax(-1)-1
        next_hidden=(hidden+self.unit_embed[choice.clamp_min(0)]*(choice>=0)[:,:,None]).tanh()
        suffix=hidden@self.rank_weights.T+self.rank_bias[left.clamp_min(0),rank.clamp_min(0)]
        return root_logits,logits,suffix,torch.cat([next_hidden,token[:,:,H:]],-1),choice

    def native(self):
        return torch.cat([p.detach().reshape(-1) for p in [self.unit_weights,self.unit_bias,self.unit_row,self.unit_embed,
                                                           self.stop,self.rank_weights,self.rank_bias]]).tolist()


def train(a,seed):
    torch.manual_seed(seed);torch.set_num_threads(1);rng=np.random.default_rng(seed)
    joins=joins_for(read(a.donor));lookup={u[0]:i for i,u in enumerate(joins)}
    names=sorted(x.stem for x in (a.targets/'train').glob('*.npz'));assert len(names)==4
    datasets=[];rank_stats=[]
    for n in names:
        with np.load(a.original/n/'training.npz') as z:x=torch.tensor(z['features']);y=torch.tensor(z['positive'])
        with np.load(a.capture/n/'ranks.npz') as z:rank=torch.tensor(z['rank']).long()
        goals=torch.zeros(len(y),y.shape[1],len(joins),dtype=torch.bool)
        with np.load(a.targets/'train'/f'{n}.npz') as z:
            for run,l,r,unit,depth,*_ in z['targets']:
                if depth==2:goals[run-1,l*R+r,lookup[unit]]=True
        datasets.append((x,y,goals,rank,np.flatnonzero(goals.any((1,2)).numpy())))
        rank_stats.append(int((rank>=0).sum()))
    model=Actor(joins);opt=torch.optim.Adam(model.parameters(),lr=.008);losses=[]
    for step in range(a.updates):
        samples=[]
        for j in range(12):
            x,y,g,rank,positive=datasets[rng.integers(len(names))]
            end=rng.choice(positive) if j%3 else rng.integers(7,len(x));start=max(0,int(end)-7)
            samples.append((x[start:start+8],y[start:start+8],g[start:start+8],rank[start:start+8]))
        x,y,g,rank=map(torch.stack,zip(*samples));prev=torch.zeros(len(x),ROWS,H+4)
        loss=0.
        for t in range(8):
            root,code,raw,prev,chosen=model.step(x[:,t],prev)
            productive=g[:,t].any(-1);target=torch.where(productive.any(1)[:,None],productive,y[:,t])
            loss=loss+leaf.set_loss(root,target)
            idx=((prev[:,:,H].long()-1)*R+prev[:,:,H+2].long()-1).clamp_min(0)
            mask=g[:,t].gather(1,idx[:,:,None].expand(-1,-1,len(joins))) & (prev[:,:,-1:]!=0)
            y_code=torch.cat([~mask.any(-1,keepdim=True),mask],-1)
            mass=(code.softmax(-1)*y_code).sum(-1).clamp_min(1e-12)
            loss=loss+(-mass.log()*torch.where(mask.any(-1),1.,.08)).mean()
            wanted=rank[:,t].gather(1,idx);defined=(wanted>=0)&(prev[:,:,-1]!=0)
            if defined.any():loss=loss+.3*nn.functional.cross_entropy(raw[defined],wanted[defined])
            # Supervise the physical-witness rank priors also on other training-only admissible roots.
            active=rank[:,t]>=0
            if active.any():
                prior=model.rank_bias.reshape(1,32*R,R).expand(len(x),-1,-1)
                loss=loss+.1*nn.functional.cross_entropy(prior[active],rank[:,t][active])
        loss=loss/8;opt.zero_grad();loss.backward();nn.utils.clip_grad_norm_(model.parameters(),1.);opt.step()
        if step%40==0:losses.append(float(loss.detach()))
    dest=a.out/f'train-{seed}';dest.mkdir(parents=True,exist_ok=False);torch.save(model.state_dict(),dest/'actor.pt')
    (dest/'model.json').write_text(json.dumps(dict(schema='eggfuse.one-emission/v1',root=model.root.metal_weights(),
        head=model.native(),joins=joins,train=names,rank_targets=rank_stats,steps=a.updates,seed=seed,loss=losses),separators=(',',':'))+'\n')
    print(seed,losses[-2:],rank_stats,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('donor','original','targets','capture','out'):p.add_argument(k,type=Path)
    p.add_argument('--updates',type=int,default=520);p.add_argument('--seeds',nargs='+',type=int,default=[1703,1709])
    a=p.parse_args()
    for seed in a.seeds:train(a,seed)

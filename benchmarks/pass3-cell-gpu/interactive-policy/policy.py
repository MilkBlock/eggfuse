"""Two learned decisions per published port. CPU only supplies an optional versioned reply."""
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from corpus import observable_features


class Selector(nn.Module):
    def __init__(self,sources):
        super().__init__()
        self.source=nn.Embedding(sources+1,16)
        self.issue=nn.Linear(8,16)
        self.transition=nn.Linear(16,16)
        self.reply=nn.Linear(7,16,bias=False)
        self.gates=nn.Linear(16,3) # primary issued, eq vs greater, optional consumer issued

    def context(self,ids,features):
        return (self.source(ids)+self.issue(features)).tanh()

    def decide(self,prior,reply):
        return self.gates((self.transition(prior)+self.reply(reply)).tanh())


def features_reply(events,modes,guard,value,sibling):
    # Modes 0,1,2,3 are no dynamic reply, guard only, exact b, and exact b plus a. Static literals are known in all arms.
    n=len(events);r=np.zeros((n,7),np.float32)
    known=events[:,9].astype(bool);adj_known=events[:,10].astype(bool)
    mode=np.broadcast_to(modes,n)
    has_guard=(known|(mode>=1))&(guard>=0)
    for c in range(3):r[:,c]=(has_guard&(guard==c))
    raw_b=known|(mode==2)|(mode==3)
    raw_a=adj_known|(mode==3)
    r[:,3]=raw_b;r[:,4]=np.where(raw_b,np.tanh((value-events[:,7])/4.),0)
    r[:,5]=raw_a;r[:,6]=np.where(raw_a,np.tanh((sibling-events[:,8])/4.),0)
    return r


def train(training,seed,updates):
    torch.manual_seed(seed);rng=np.random.default_rng(seed)
    vocab={x:i+1 for i,x in enumerate(sorted({(int(row[2]),int(row[3])) for ports,_ in training.values() for row in ports.events}))}
    net=Selector(len(vocab));opt=torch.optim.AdamW(net.parameters(),lr=.006,weight_decay=.005)
    ds=[]
    for ports,truth in training.values():
        e=ports.events;ids,x=observable_features(e,vocab)
        g=np.where(e[:,5]==e[:,7],1,np.where(e[:,5]>e[:,7],2,0))
        reps=np.stack([features_reply(e,m,g,e[:,5],e[:,6]) for m in range(4)],1)
        ds.append((ids,x,reps,truth.astype(np.float32)))
    losses=[]
    for step in range(updates):
        ids,x,reply,truth=ds[step%len(ds)]
        ix=rng.integers(len(ids),size=64);m=rng.integers(4,size=len(ix))
        ctx=net.context(torch.from_numpy(ids[ix]),torch.from_numpy(x[ix]))
        logits=net.decide(ctx,torch.from_numpy(reply[ix,m]));labels=torch.from_numpy(truth[ix])
        any_primary=labels[:,:2].sum(1)
        gates=F.binary_cross_entropy_with_logits(logits[:,0],any_primary)+F.binary_cross_entropy_with_logits(logits[:,2],labels[:,2])
        branch=F.binary_cross_entropy_with_logits(logits[:,1],labels[:,1],reduction='none')
        loss=gates+(branch*any_primary).sum()/any_primary.sum().clamp_min(1)
        opt.zero_grad();loss.backward();opt.step()
        if step%75==0:losses.append(float(loss.detach()))
    return net.eval(),vocab,losses

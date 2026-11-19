"""Two simultaneous row proposals for a pair of generated Cell instances."""
import torch
from torch import nn


class PairActor(nn.Module):
    def __init__(self):
        super().__init__()
        self.register_buffer('pairs',torch.combinations(torch.arange(8),r=2),persistent=False)
        disjoint=(self.pairs[:,None,:,None]!=self.pairs[None,:,None,:]).all(-1).all(-1)
        self.register_buffer('assignments',disjoint.nonzero(),persistent=False)
        self.score=nn.Sequential(nn.Linear(17,32),nn.Tanh(),nn.Linear(32,1))

    def forward(self,token,requests,collision=False):
        active=token[...,32:34].argmax(-1).float()
        rows=token[...,50:55].int()
        b=token[...,42:50].argmax(-1)
        origins=requests[...,2:4].reshape(len(rows),2,2,2).transpose(1,2)
        if collision:
            origins=origins[:,:1].expand(-1,2,-1,-1)
        hit=(rows[:,None,:,None,:2]==origins[:,:,None,:,:]).all(-1).float()
        left,right=self.pairs.unbind(-1)
        # Each side contributes its activity, its demand and four continuous
        # channels of the actual generated instance. The shared head also sees
        # the emitted B address relation. No valid-pair mask enters first choice.
        summary=token[...,:32].unflatten(-1,(4,8)).mean(-1)
        member=torch.cat((active[...,None],summary),-1)[:,None].expand(-1,2,-1,-1)
        member=torch.cat((member,hit),-1)
        same_b=(b[:,left]==b[:,right]).float()
        extras=torch.stack((same_b,(rows[:,left,0]==rows[:,right,0]).float(),
                            (rows[:,left,4]==rows[:,right,4]).float()),-1)
        features=torch.cat((member[:,:,left],member[:,:,right],extras[:,None].expand(-1,2,-1,-1)),-1)
        return self.score(features).squeeze(-1)


def projected_utility(token,requests,pairs,collision=False):
    """Score actual emitted references by the number of assigned requests they serve."""
    left,right=pairs.unbind(-1)
    active=token[...,32:34].argmax(-1).bool()
    parent=token[...,42:50].argmax(-1)
    valid=active[:,left]&active[:,right]&(parent[:,left]==parent[:,right])
    origins=requests[...,2:4].reshape(len(token),2,2,2).transpose(1,2)
    if collision:
        origins=origins[:,:1].expand(-1,2,-1,-1)
    hits=(token[:,None,:,None,50:52]==origins[:,:,None,:,:]).all(-1)
    demand=(hits[:,:,left]|hits[:,:,right]).float().sum(-1)
    return torch.where(valid[:,None],1+demand,-3.)


def choose(scores,pairs,free=None):
    if free is not None:
        allowed=free[:,pairs[:,0]] & free[:,pairs[:,1]]
        scores=scores.masked_fill(~allowed[:,None],float('-inf'))
    return pairs[scores.argmax(-1)].int().contiguous()

def joint_choices(scores,pairs,assignments):
    left,right=assignments.unbind(-1)
    choice=(scores[:,0,left]+scores[:,1,right]).argmax(-1)
    return pairs[assignments[choice]].int().contiguous()

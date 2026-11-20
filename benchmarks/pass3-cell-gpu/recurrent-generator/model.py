"""A shared two-row autoregressive proposer. A token contains latent, leaf, row address, rank and presence."""
import torch
from torch import nn

LEAVES,RANKS,HIDDEN,ROWS,SETS=32,8,8,2,32

class Actor(nn.Module):
    def __init__(self):
        super().__init__()
        def matrix(*shape):return nn.Parameter(torch.randn(shape)*0.1)
        self.recurrent=matrix(HIDDEN,HIDDEN)
        self.previous=matrix(HIDDEN,3)
        self.stages=matrix(SETS,HIDDEN)
        self.rows=matrix(ROWS,HIDDEN)
        self.templates=matrix(LEAVES+1,HIDDEN)
        self.positions=matrix(RANKS,HIDDEN)
        self.read=matrix(HIDDEN,6)
        self.bias=matrix(LEAVES)
        self.local_score=matrix(6)
        self.abstain=matrix(HIDDEN+1)
        self.register_buffer('scale',torch.tensor([32.,32.,2.,16.,32.,16.]),persistent=False)

    def step(self,observations,previous,intervention='intact'):
        batch=observations.shape[0]
        latent=previous[:,:,:HIDDEN]
        if intervention=='zero-latent':latent=torch.zeros_like(latent)
        if intervention=='swap-latent':latent=latent.flip(1)
        leaf=previous[:,:,HIDDEN].long()
        prev_values=previous[:,:,HIDDEN+1:]/previous.new_tensor([16384.,float(RANKS),1.])
        stage=observations[:,0,1].long()%SETS
        state=(latent@self.recurrent.T+prev_values@self.previous.T+
               self.templates[leaf]+self.stages[stage,None,:]+self.rows).tanh()
        features=observations[:,:,2:].float()/self.scale
        static=(self.templates[1:,None]+self.positions).reshape(1,LEAVES*RANKS,HIDDEN)
        keys=(static+features@self.read.T).tanh()
        score=state@keys.transpose(1,2)+self.bias.repeat_interleave(RANKS)+ (features@self.local_score)[:,None]
        score=score.masked_fill(observations[:,None,:,0]<0,-1e4)
        null=(state@self.abstain[:HIDDEN]+self.abstain[-1])[:,:,None]
        logits=torch.cat([null,score],dim=-1)
        choice=logits.argmax(-1);idx=(choice-1).clamp_min(0)
        picked=keys.gather(1,idx[:,:,None].expand(-1,-1,HIDDEN))*(choice!=0)[:,:,None]
        if self.training:
            soft=logits.softmax(-1)[:,:,1:]@keys
            picked=picked+(soft-soft.detach())
        active=(choice!=0).float()
        discrete=torch.stack([(idx//RANKS+1)*active,(observations[:,:,0].gather(1,idx)+1)*active,
                              (idx%RANKS+1)*active,active],-1)
        return logits,torch.cat([(state+picked).tanh(),discrete],-1)

    def metal_weights(self):
        return torch.cat([getattr(self,k).detach().reshape(-1) for k in (
            'recurrent','previous','stages','rows','templates','positions','read','bias','local_score','abstain')]).tolist()

def set_loss(logits,target):
    prob=logits.softmax(-1);left,right=prob[:,0,1:]*target,prob[:,1,1:]*target
    n=target.sum(-1)
    any_left,any_right=left.sum(-1),right.sum(-1)
    both=any_left*any_right-(left*right).sum(-1)
    one=any_left*prob[:,1,0]+any_right*prob[:,0,0]
    empty=prob[:,0,0]*prob[:,1,0]
    mass=torch.where(n==0,empty,torch.where(n==1,one,both))
    return (-mass.clamp_min(1e-12).log()*torch.where(n==0,.15,1.)).mean()

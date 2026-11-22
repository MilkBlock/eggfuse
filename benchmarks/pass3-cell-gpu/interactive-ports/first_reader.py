"""Train a first-port read using only visible port fields and a shared set summary."""
import torch
from torch import nn
from policy import WIDTH, TABLES


class FirstReader(nn.Module):
    def __init__(self, width, context=True):
        super().__init__()
        self.context=context
        self.encode=nn.Sequential(nn.Linear(WIDTH,width),nn.Tanh())
        self.message=nn.Linear(width,width)
        self.gate=nn.Linear(width,1)
        self.query=nn.Linear(width,width)
        self.local=nn.Linear(width,1)
        self.stop=nn.Parameter(torch.zeros(1))

    def forward(self,bank):
        h=self.encode(bank)
        local=self.local(h).squeeze(-1)
        if self.context:
            summary=(self.message(h)*self.gate(h).sigmoid()).sum(1)
            local=local+(self.query(h)*summary[:,None]).sum(-1)/h.shape[-1]**.5
        return torch.cat((self.stop.expand(len(h),1),local),1)


class SharedScalarReader(nn.Module):
    """A common scalar basis for sending and reading. All role weights are learned."""
    def __init__(self):
        super().__init__()
        roles=WIDTH-8
        self.sender=nn.Linear(roles,1)
        self.receiver=nn.Linear(roles,1)
        self.local=nn.Linear(roles,1)
        self.amplitude=nn.Parameter(torch.tensor(1.))
        self.stop=nn.Parameter(torch.zeros(1))

    def forward(self,bank):
        start=len(TABLES)
        scalar=bank[:,:,start:start+8]
        roles=torch.cat((bank[:,:,:start],bank[:,:,start+8:]),-1)
        summary=(scalar*self.sender(roles)).sum(1)
        evidence=(scalar*summary[:,None]).sum(-1)
        scores=self.local(roles).squeeze(-1)+self.amplitude*self.receiver(roles).squeeze(-1)*evidence
        return torch.cat((self.stop.expand(len(bank),1),scores),1)


def examples(generator,batch,dense,target,diverse=False):
    # Unique L and R values within each table. Their possible overlap is not
    # exposed in model inputs. Random facts can be retired before this Run.
    n=3 if dense else 1
    rand=lambda *size:torch.rand(size,generator=generator)
    left=rand(batch,8).argsort()[:,:n]
    permutation=rand(batch,8).argsort()
    free=permutation[~(permutation[:,:,None]==left[:,None,:]).any(-1)].reshape(batch,8-n)
    right=free[:,:n].clone()
    pos=rand(batch,n).argmax(1)
    include=rand(batch)<.65
    indices=torch.arange(batch)
    right[include,-1]=left[indices,pos][include]
    ids=torch.cat((left,right),1)
    bank=torch.zeros(batch,2*n+2,WIDTH)
    bank[:,:n,0]=1
    bank[:,n:2*n,1]=1
    bank[:,:2*n,len(TABLES):len(TABLES)+8].scatter_(2,ids[:,:,None],1)
    bank[:,2*n:,2]=1
    if diverse:
        # Real ingress includes scalar-bearing Tags and existing constructor outputs.
        extras=(rand(batch,2)*len(TABLES)).long().clamp_min(2)
        bank[:,2*n:]=0
        bank[:,2*n:,:len(TABLES)].scatter_(2,extras[:,:,None],1)
        extra_keys=(rand(batch,2)*8).long()
        bank[:,2*n:,len(TABLES):len(TABLES)+8].scatter_(2,extra_keys[:,:,None],(extras==2).float()[:,:,None])
    retired=rand(batch,2*n)<.08
    bank[:,:2*n,-1]=retired
    possible=(left[:,:,None]==right[:,None,:]) & ~retired[:,None,n:]
    valid=~retired[:,:n]
    if target=='productive':
        valid=valid & possible.any(-1)
    labels=torch.zeros(batch,bank.shape[1]+1,dtype=torch.bool)
    labels[:,1:n+1]=valid
    labels[:,0]=~valid.any(1)
    return bank,labels


def fit(seed,width,context,dense,target,steps,diverse=False):
    torch.manual_seed(seed)
    model=SharedScalarReader() if width==0 else FirstReader(width,context)
    opt=torch.optim.Adam(model.parameters(),lr=.006)
    rng=torch.Generator().manual_seed(seed+1000)
    for _ in range(steps):
        bank,labels=examples(rng,64,dense,target,diverse)
        scores=model(bank)
        loss=(scores.logsumexp(1)-scores.masked_fill(~labels,-torch.inf).logsumexp(1)).mean()
        opt.zero_grad()
        loss.backward()
        opt.step()
    return model.eval()

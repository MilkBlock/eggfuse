"""Set pointer policy. Indices are used only to copy the selected opaque handle."""
import random
import torch
from torch import nn

TABLES=('L','R','Tag','Both','C','D','Use')
ROLES=('left','right','advance','independent','use')
WIDTH=len(TABLES)+8+3


def fields(table, scalar=None, composite=False, port=0,retired=False):
    x=[0.]*WIDTH
    x[TABLES.index(table)]=1.
    if scalar is not None:
        x[len(TABLES)+scalar]=1.
    x[-3:]=[float(composite),float(port),float(retired)]
    return x


class Pointer(nn.Module):
    def __init__(self):
        super().__init__()
        self.keys=nn.Linear(WIDTH,32)
        self.roles=nn.Embedding(len(ROLES),32)
        self.condition=nn.Linear(WIDTH,32,bias=False)
        self.stop=nn.Linear(32,1)
        self.block=nn.Linear(2,1)
        self.skip=nn.Linear(1,1)

    def logits(self,bank,role,selected):
        query=self.roles.weight[role]+self.condition(selected)
        return self.score_keys(self.keys(bank),query)

    def score_keys(self,keys,query):
        scores=(keys*query[:,None]).sum(-1)
        return torch.cat((self.stop(query),scores),-1)

    def macro_logit(self,selected):
        # Issuance sees its own selected input values, never the fork outcome.
        scalar=selected[len(TABLES):len(TABLES)+8]
        return self.block(torch.stack((scalar.sum(),scalar@torch.linspace(0,1,8))))[0]


def train(seed):
    torch.manual_seed(seed)
    model=Pointer()
    optimizer=torch.optim.Adam(model.parameters(),lr=.012)
    rng=random.Random(seed)
    for step in range(650):
        banks=[];queries=[];targets=[]
        role=step%len(ROLES)
        want=('L','R','Both','Tag','C')[role]
        for _ in range(48):
            k=rng.randrange(8)
            selected=fields('L',k) if role==1 else [0.]*WIDTH
            rows=[]
            labels=[]
            for _ in range(9):
                t=rng.choice(TABLES)
                v=rng.randrange(8)
                full=rng.choice((True,False)) if t in ('Both','C') else False
                port=int(t=='C' and full)
                retired = rng.random()<.18
                rows.append(fields(t,v if t in ('L','R','Tag') else None,full,port,retired))
                labels.append(not retired and t==want and (role!=1 or v==k))
            if role==1 and rng.random()<.5:
                j=rng.randrange(len(rows))
                rows[j]=fields('R',k)
                labels[j]=True
            # Equivalent live aliases share credit. For measuring ownership on
            # a fresh compound export, include cases with both old and new C.
            banks.append(rows);queries.append(selected);targets.append([not any(labels),*labels])
        scores=model.logits(torch.tensor(banks),role,torch.tensor(queries))
        valid=torch.tensor(targets)
        loss=(scores.logsumexp(-1)-scores.masked_fill(~valid,-torch.inf).logsumexp(-1)).mean()
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
    return model.eval()

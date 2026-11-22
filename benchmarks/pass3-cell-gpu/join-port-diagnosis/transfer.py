"""Synthetic training and held-out inference on real two-table EggCC Run snapshots."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import torch
from torch import nn
from torch.nn import functional as F


class JoinReader(nn.Module):
    def __init__(self,bins,structured=False):
        super().__init__()
        self.bins=bins
        self.structured=structured
        self.left_gate=nn.Linear(2,1) if structured else None
        self.messages=nn.Linear(2,2)
        self.first=nn.Sequential(nn.Linear(4,16),nn.Tanh(),nn.Linear(16,1))
        self.second=nn.Sequential(nn.Linear(4,16),nn.Tanh(),nn.Linear(16,1))

    def roots(self,state,codes):
        # Every live input contributes to each summary; no relation/type filter
        # or exact equality lookup is provided to either pointer head.
        weight=self.messages(state).sigmoid()
        hot=F.one_hot(codes,self.bins).float()
        summary=(hot[:,:,:,:,None]*weight[:,:,None,None,:]).amax(dim=1)
        hit=(hot[:,:,:,:,None]*summary[:,None]).sum(dim=3).amin(dim=2)
        if self.structured:
            # Two monotone summaries predict live right / fresh right.
            # Fresh roots may use either; older roots need the fresh summary.
            available=torch.where(state[:,:,1]>0,hit[:,:,0],hit[:,:,1])
            return torch.minimum(self.left_gate(state).squeeze(-1),
                                 torch.logit(available.clamp(1e-6,1-1e-6)))
        return self.first(torch.cat((state,hit),dim=-1)).squeeze(-1)

    def followers(self,state,codes,root_state,root_codes):
        # Fraction of equal categorical fingerprint components, computed for
        # all rows for each selected first port. Receiver retains exact values.
        overlap=(codes[:,None]==root_codes[:,:,None]).float().mean(-1)
        n=state.shape[1]
        x=state[:,None].expand(-1,root_state.shape[1],-1,-1)
        fresh=root_state[:,:,None,1].expand(-1,-1,n)
        return self.second(torch.cat((x,fresh[:,:,:,None],overlap[:,:,:,None]),-1)).squeeze(-1)


def train(model,seed,steps):
    rng=torch.Generator().manual_seed(seed)
    opt=torch.optim.Adam(model.parameters(),lr=.015)
    for step in range(steps):
        b,n=16,(8,16,24)[step%3]
        role=torch.randint(0,2,(b,n),generator=rng)
        fresh=torch.randint(0,2,(b,n),generator=rng)
        state=torch.stack((role,fresh),-1).float()
        symbols=torch.randint(0,n*2,(b,n),generator=rng)
        dictionary=torch.randint(model.bins,(b,n*2,4),generator=rng)
        codes=dictionary[torch.arange(b)[:,None],symbols]
        # Hard negatives share three fingerprints but differ in the fourth.
        if step%2:
            dictionary[:,1::2,:3]=dictionary[:,::2,:3]
            codes=dictionary[torch.arange(b)[:,None],symbols]
        target=((symbols[:,:,None]==symbols[:,None]) & (role[:,:,None]==0) &
                (role[:,None]==1) & ((fresh[:,:,None]+fresh[:,None])>0))
        roots=model.roots(state,codes)
        candidates=model.followers(state,codes,state,codes)
        def balanced(scores,labels):
            pos=-F.logsigmoid(scores)[labels]
            neg=-F.logsigmoid(-scores)[~labels]
            return neg.mean()+(pos.mean() if pos.numel() else 0)
        left=(role==0)[:,:,None].expand_as(target)
        loss=balanced(roots,target.any(-1))+balanced(candidates[left],target[left])
        if model.structured:
            gate_targets=torch.stack((role==1,(role==1)&(fresh==1)),-1).float()
            loss=loss+F.binary_cross_entropy_with_logits(model.messages(state),gate_targets)
            loss=loss+F.binary_cross_entropy_with_logits(model.left_gate(state).squeeze(-1),(role==0).float())
        opt.zero_grad();loss.backward();opt.step()


@torch.no_grad()
def evaluate(model,path):
    totals=Counter()
    cases=json.load(gzip.open(path))
    for case in cases:
        rows=case['rows']
        if not rows:
            continue
        keys=[json.dumps(r[1],sort_keys=True,separators=(',',':')) for r in rows]
        codes=torch.tensor([[v%model.bins for v in hashlib.sha256(k.encode()).digest()[:4]] for k in keys])
        state=torch.tensor([[role,float(not case['delta'] or epoch>=case['wm'])] for role,_,_,epoch in rows])
        lhs=state[:,0]==0
        # Exact reference for this frozen source snapshot. No reference mask
        # enters the model; both axes on the model path contain all live rows.
        exact=torch.tensor([[a==b for b in keys] for a in keys]) & lhs[:,None] & ~lhs[None] & (state[:,1,None]+state[None,:,1]>0)
        scores=model.roots(state[None],codes[None])[0]
        selected=(scores>0).nonzero().flatten()
        proposed=torch.zeros_like(exact)
        if len(selected):
            proposed[selected]=model.followers(state[None],codes[None],state[None,selected],codes[None,selected])[0]>0
        totals.update(cases=1,ports=len(keys),truth=exact.sum().item(),paid=proposed.sum().item(),
                      missing=(exact&~proposed).sum().item(),spurious=(~exact&proposed).sum().item(),
                      exact_cases=int(torch.equal(exact,proposed)),productive=int(exact.any()),
                      productive_exact=int(exact.any() and torch.equal(exact,proposed)),
                      second_scores=len(selected)*len(keys),root_scores=len(keys),
                      all_left_second_scores=int(lhs.sum())*len(keys),
                      first_misses=(exact.any(-1)&(scores<=0)).sum().item())
    return totals


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('out',type=Path)
    p.add_argument('banks',type=Path,nargs='+')
    p.add_argument('--steps',type=int,default=900)
    p.add_argument('--bins',type=int,default=32)
    p.add_argument('--checkpoint',type=Path)
    p.add_argument('--structured',action='store_true')
    p.add_argument('--seed',type=int,default=1703)
    a=p.parse_args()
    torch.set_num_threads(1)
    torch.manual_seed(a.seed)
    m=JoinReader(a.bins,a.structured)
    if a.checkpoint:
        m.load_state_dict(torch.load(a.checkpoint,weights_only=True))
    else:
        train(m,a.seed,a.steps)
    report={bank.stem:evaluate(m.eval(),bank) for bank in a.banks}
    a.out.write_text(json.dumps(report,indent=2)+'\n')
    if not a.checkpoint:
        torch.save(m.state_dict(),a.out.with_suffix('.pt'))
    print(report,flush=True)

"""A shared learned score for named reads below the frozen Actor's issuance threshold."""
from pathlib import Path
import math

import torch
from torch import nn

from alternate_proofs import digest
from higher_cell import read


class RecoveryHead(nn.Module):
    def __init__(self,width):
        super().__init__()
        self.context=nn.Linear(2*width,24)
        self.port=nn.Linear(width,24,bias=False)
        self.evidence=nn.Linear(8,24,bias=False)
        self.output=nn.Linear(24,1)

    def inputs(self,context,port,evidence):
        return self.context(context)+self.port(port)+self.evidence(evidence)

    def forward(self,context,port,evidence):
        return self.output(self.inputs(context,port,evidence).tanh()).squeeze(-1)


class RecurrentRecoveryHead(RecoveryHead):
    def __init__(self,width,steps):
        super().__init__(width)
        if steps < 1:
            raise ValueError('expected a positive number of recurrent steps')
        self.steps=steps
        self.refine=nn.Linear(self.output.in_features,self.output.in_features,bias=False)

    def forward(self,context,port,evidence):
        inputs=self.inputs(context,port,evidence)
        state=inputs.tanh()
        for _ in range(self.steps):
            state=(inputs+self.refine(state)).tanh()
        return self.output(state).squeeze(-1)


def features(cat,mem,rid,order,depth,prefix,ids,margin):
    role=order[depth]
    static=mem.nodes[cat.roots['generated',rid]]+mem.nodes[cat.atoms[rid][role][1]]
    prior=mem.keys[prefix].mean(1) if depth else static.new_zeros(len(prefix),len(static))
    ctx=torch.cat((static.expand_as(prior),prior),1)
    links=[(j,src,dst) for j,p in enumerate(order[:depth]) for src,dst in cat.field_links[rid,p,role]]
    lo=torch.ones_like(margin)
    total=torch.zeros_like(margin)
    for j,src,dst in links:
        sim=mem.fields[prefix[:,j],src]@mem.fields[ids,dst].T/64
        lo=torch.minimum(lo,sim)
        total+=sim
    scalars=margin.new_tensor([math.log1p(len(order)),math.log1p(depth),float(depth+1==len(order)),
                               math.log1p(len(links)),math.log1p(len(ids))])
    evidence=torch.cat((margin.clamp(-32,0)[:,:,None]/8,lo[:,:,None],
                        (total/max(len(links),1))[:,:,None],scalars.expand(*margin.shape,-1)),dim=-1)
    return ctx,mem.keys[ids],evidence


class Recovery:
    def __init__(self,folder,weights,*,margin_only=False):
        folder=Path(folder)
        meta=read(folder/'training.json')
        if meta['base']!=digest(weights) or meta['head']!=digest(folder/'head.pt'):
            raise ValueError('prefix recovery checkpoint differs from its frozen Actor')
        self.refinements=meta.get('refinements',0)
        width=meta['width']
        self.head=(RecurrentRecoveryHead(width,self.refinements) if self.refinements else RecoveryHead(width)).eval()
        self.head.load_state_dict(torch.load(folder/'head.pt',map_location='cpu',weights_only=True))
        self.margin_only=margin_only
        self.cut=meta['margin_cut'] if margin_only else meta['cut']
        self.budget=meta['budget']
        self.checkpoint=meta['head']
        self.read_order=meta.get('read_order','source')

    def scores(self,cat,mem,rid,order,depth,prefix,ids,margin):
        if self.margin_only:
            return margin
        ctx,ports,ev=features(cat,mem,rid,order,depth,prefix,ids,margin)
        return self.head(ctx[:,None],ports[None,:],ev)


def bounded_indices(scores,k):
    if len(scores)<=k:
        return torch.arange(len(scores),device=scores.device)
    values,indices=scores.topk(k+1)
    # Omit the entire tie crossing the boundary. Never sort opaque addresses.
    return indices[:k][values[:k]>values[k]]


def select(model,cat,mem,dom,rid,anchor,order,depth,frontier,policy,count):
    from prefix_policy import score_tiles
    k=policy.top_k
    if k is None or policy.verify or policy.audit:
        raise ValueError('learned recovery needs a fixed beam and search-free verification')
    normal=[]
    normal_scores=[]
    extra=[]
    extra_scores=[]
    cut=model.thresholds[1 if depth==0 else 2]
    for prefix,ids,scores in score_tiles(model,cat,mem,dom,rid,anchor,order,depth,frontier):
        good=scores>=cut
        i,j=good.nonzero(as_tuple=True)
        count['scored']+=scores.numel()
        count['above_threshold']+=len(i)
        normal.append(torch.cat((prefix[i],ids[j,None]),1))
        normal_scores.append(scores[i,j])
        if good.all():
            continue
        recovery=policy.recovery.scores(cat,mem,rid,order,depth,prefix,ids,scores-cut)
        add=(~good)&(recovery>=policy.recovery.cut)
        i,j=add.nonzero(as_tuple=True)
        count['recovery_scored']+=recovery.numel()
        count['recovery_qualified']+=len(i)
        extra.append(torch.cat((prefix[i],ids[j,None]),1))
        extra_scores.append(recovery[i,j])
    if not normal:
        return frontier.new_empty((0,depth+1))
    normal_scores=torch.cat(normal_scores)
    which=bounded_indices(normal_scores,k)
    points=torch.cat(normal)[which]
    allocate=policy.allocation is not None and depth+1==len(order)
    if allocate:
        priorities=normal_scores[which]-cut
    available=min(max(0,k-sum(map(len,normal))),policy.recovery.budget)
    if available and extra:
        extra_scores=torch.cat(extra_scores)
        which=bounded_indices(extra_scores,available)
        take=torch.cat(extra)[which]
        if allocate:
            margin=extra_scores[which]-policy.recovery.cut
            priorities=torch.cat((priorities,-1/(1+margin)))
        count['recovery_added']+=len(take)
        points=torch.cat((points,take))
    if allocate and len(points):
        points=policy.allocation.select(cat,mem,rid,order,points,priorities,count)
    count['after_cap']+=len(points)
    return points

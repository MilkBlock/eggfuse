"""One compositional scorer for a catalog of variable-size, typed Cell instruction graphs."""
import math

import torch
from torch import nn

from actor import rotate, row_features


def positional(width, index):
    return rotate(torch.ones(1,width),torch.tensor([index]))[0]


def compile_graphs(layouts, catalog, nodes):
    """Compile every atom edge to its consumer role and exact producer instruction."""
    width=nodes.shape[1]
    count=len(layouts)
    length=max(map(len,layouts))
    fan=max(len(wires) for layout in layouts for _,_,wires in layout)
    steps=nodes.new_zeros(count,length,width)
    valid=torch.zeros(count,length,dtype=torch.bool)
    edges=nodes.new_zeros(count,length,fan,width)
    incoming=torch.zeros(count,length,fan,dtype=torch.long)
    used=torch.zeros(count,length,fan,dtype=torch.bool)
    positions={}
    def position(k):
        if k not in positions:
            positions[k]=positional(width,k)
        return positions[k]
    for n,layout in enumerate(layouts):
        for j,(rid,group,wires) in enumerate(layout):
            tmpl='generated',rid
            steps[n,j]=nodes[catalog.roots[tmpl]]+position(group)
            valid[n,j]=True
            if len(wires)!=len(catalog.inputs[tmpl]):
                raise ValueError('wrong template arity')
            for role,(owner,slot) in enumerate(wires):
                atom=nodes[catalog.inputs[tmpl][role]]
                if owner<0:
                    source=position(slot)
                elif owner<j:
                    pc_node=catalog.outputs[('generated',layout[owner][0]),slot]
                    source=nodes[pc_node]+position(slot)
                    incoming[n,j,role]=owner+1
                else:
                    raise ValueError('forward reference in a Cell')
                edges[n,j,role]=rotate((source+atom)[None],torch.tensor([role]))[0]
                used[n,j,role]=True
    return steps,valid,edges,incoming,used


class CellScorer(nn.Module):
    def __init__(self,width):
        super().__init__()
        self.step=nn.Linear(width,width)
        self.edge=nn.Linear(width,width)
        self.message=nn.Linear(width,width,bias=False)
        self.context=nn.Linear(width,width)
        self.head=nn.Sequential(nn.Linear(3*width,width),nn.Tanh(),nn.Linear(width,2))

    def encode(self,graphs):
        steps,valid,edges,incoming,used=graphs
        n,length,width=steps.shape
        states=[steps.new_zeros(n,width)]
        ids=torch.arange(n,device=steps.device)[:,None]
        for j in range(length):
            parents=torch.stack(states,1)[ids,incoming[:,j]]
            messages=(self.edge(edges[:,j])+self.message(parents)).tanh()*used[:,j,:,None]
            x=self.step(steps[:,j])+messages.sum(1)/used[:,j].sum(1).clamp_min(1)[:,None].sqrt()
            states.append(x.tanh()*valid[:,j,None])
        return torch.stack(states[1:],1).sum(1)/valid.sum(1)[:,None].sqrt()

    def forward(self,context,templates):
        context=self.context(context).tanh()
        return self.head(torch.cat((context,templates,context*templates),dim=-1))


def root_context(hashes,width):
    # Encode only the named parents already supplied by the root Actor.
    if not hashes:
        return torch.zeros(width)
    values=row_features([tuple(row) for row in hashes],width,'cpu')
    return rotate(values,torch.arange(len(values))).sum(0)/math.sqrt(len(values))

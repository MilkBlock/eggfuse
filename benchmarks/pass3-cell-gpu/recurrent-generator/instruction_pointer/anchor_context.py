"""A learned anchor read over the other typed parent domains of this sealed Run."""
import torch
from torch import nn

from anchor_set import AnchorSetActor


class ContextActor(AnchorSetActor):
    def __init__(self,vocabulary,names='structural',blind=False,width=32):
        super().__init__(vocabulary,names,width)
        self.blind=blind
        self.context_field=nn.Linear(64,16,bias=False)
        self.context_port=nn.Linear(width,16,bias=False)
        self.context_value=nn.Linear(width,width,bias=False)
        self.context_gate=nn.Linear(3*width+2,width)
        self.context_score=nn.Linear(width,1,bias=False)
        nn.init.zeros_(self.context_score.weight)

    def features(self,mem,rows,column):
        logits=(self.context_port(mem.keys[rows]) if column is None else
                self.context_field(mem.fields[rows,column]))
        return (3*logits).softmax(-1)

    def summary(self,cat,mem,dom,rid,anchor,role,column):
        table=cat.atoms[rid][role][0]
        wm=mem.rules[rid] if cat.seminaive[rid] and role<anchor else None
        cache_key=(table,wm,column)
        if cache_key not in dom.summaries:
            rows=dom.role(cat,mem,rid,anchor,role)
            if not len(rows):
                width=self.context_port.out_features
                empty=mem.keys.new_zeros(width),mem.keys.new_zeros((width,self.width)),0
                dom.summaries[cache_key]=empty
                return empty
            keys=self.features(mem,rows,column)
            values=self.context_value(mem.keys[rows])
            dom.summaries[cache_key]=keys.sum(0),keys.T@values,len(rows)
        return dom.summaries[cache_key]

    def root_scores(self,cat,mem,rid,role,ids,dom):
        base=super().root_scores(cat,mem,rid,role,ids,dom)
        atoms=cat.atoms[rid]
        if role is None or len(atoms)<2: return base
        hidden=mem.keys[ids]
        total=hidden.new_zeros(len(ids))
        for other,(_,node) in enumerate(atoms):
            if other==role: continue
            links=cat.field_links[rid,role,other] or [(None,None)]
            for src,dst in links:
                if self.blind:
                    values=torch.zeros_like(hidden)
                    size=hidden.new_zeros((len(ids),2))
                else:
                    weights,weighted_values,n=self.summary(cat,mem,dom,rid,role,other,dst)
                    q=self.features(mem,ids,src)
                    mass=q@weights
                    values=(q@weighted_values)/mass.clamp_min(1e-6)[:,None]
                    size=torch.stack((mass.log1p(),mass.new_full(mass.shape,n).log1p()),dim=1)
                read=torch.cat((hidden,mem.nodes[node].expand_as(hidden),values,size),dim=-1)
                total=total+self.context_score(self.context_gate(read).tanh())[:,0]/len(links)
        return base+total/(len(atoms)-1)

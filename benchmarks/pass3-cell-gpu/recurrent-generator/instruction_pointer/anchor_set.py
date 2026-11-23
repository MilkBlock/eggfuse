"""One batch of named requests from the sealed snapshot, with first-fresh ownership."""
import math
from collections import defaultdict

import torch
from torch import nn

from actor import ints
from semantic_catalog import SemanticActor
from typed_content import TypedContentCatalog


class Domains:
    def __init__(self,mem):
        tables=defaultdict(list)
        for j,port in enumerate(mem.ports):
            tables[port.table].append(j)
        self.rows={t:ints(mem.nodes,js) for t,js in tables.items()}
        self.empty=ints(mem.nodes,[])
        self.versions=ints(mem.nodes,[p.version for p in mem.ports])
        self.cache={}
        self.summaries={}

    def role(self,cat,mem,rid,anchor,role):
        t=cat.atoms[rid][role][0]
        rows=self.rows.get(t,self.empty)
        if not cat.seminaive[rid] or role>anchor:
            return rows
        wm=mem.rules[rid]
        fresh=role==anchor
        key=(t,wm,fresh)
        if key not in self.cache:
            self.cache[key]=rows[(self.versions[rows]>=wm)==fresh]
        return self.cache[key]


class AnchorSetActor(SemanticActor):
    default_waves=1

    def __init__(self,vocabulary,names='structural',width=32):
        super().__init__(vocabulary,names,width)
        self.anchor_key=nn.Linear(width,width)
        self.anchor_query=nn.Linear(2*width,width)
        self.anchor_bias=nn.Linear(2*width,1)
        self.anchor_empty=nn.Linear(width,1)
        self.pair_query=nn.Linear(2*width,width)
        self.pair_bias=nn.Linear(2*width,1)
        self.pair_key=nn.Linear(width,width)
        self.field_comparison=nn.Linear(2,1,bias=False)
        self.register_buffer('thresholds',torch.zeros(3))

    def root_scores(self,cat,mem,rid,role,ids,dom):
        root=mem.nodes[cat.roots['generated',rid]]
        if role is None:
            return self.anchor_empty(root)
        h=torch.cat((root,mem.nodes[cat.atoms[rid][role][1]]))
        return self.anchor_key(mem.keys[ids])@self.anchor_query(h)/math.sqrt(self.width)+self.anchor_bias(h)

    def pair_components(self,cat,mem,rid,ordered,prefix,role,ids,measure=False):
        roles=[mem.nodes[node] for _,node in cat.atoms[rid]]
        h=mem.nodes[cat.roots['generated',rid]].expand(len(prefix),-1)
        fields=mem.keys.new_zeros((len(prefix),len(ids)))
        same=torch.zeros_like(fields)
        discrepancy=torch.zeros_like(fields) if measure else None
        for j,prior in enumerate(ordered):
            previous=prefix[:,j]
            h=self.next_read(mem.keys[previous]+roles[prior],h)
            same=same+(previous[:,None]==ids[None,:])
            for src,dst in cat.field_links[rid,prior,role]:
                similarity=mem.fields[previous,src]@mem.fields[ids,dst].T/64
                fields=fields+similarity
                if measure:
                    discrepancy=torch.maximum(discrepancy,1-similarity)
        query=torch.cat((h,roles[role].expand_as(h)),-1)
        base=self.pair_query(query)@self.pair_key(mem.keys[ids]).T/math.sqrt(self.width)
        scores=base+self.pair_bias(query)+self.field_comparison(torch.stack((fields,same),-1)).squeeze(-1)
        return scores,discrepancy

    def pair_scores(self,cat,mem,rid,ordered,prefix,role,ids):
        return self.pair_components(cat,mem,rid,ordered,prefix,role,ids)[0]

    def expand(self,cat,mem,dom,rid,anchor,first):
        order=[anchor]+[j for j in range(len(cat.atoms[rid])) if j!=anchor]
        def extend(depth,prefix):
            if depth==len(order):
                for row in prefix.cpu().tolist():
                    refs=[None]*len(order)
                    for j,i in zip(order,row,strict=True):
                        refs[j]=mem.ports[i].address
                    yield rid,tuple(refs)
                return
            role=order[depth]
            ids=dom.role(cat,mem,rid,anchor,role)
            if not len(ids):
                return
            # Tile the dense pointer evaluation without pruning candidates.
            size=max(1,65536//len(ids))
            for batch in prefix.split(size):
                scores=self.pair_scores(cat,mem,rid,order[:depth],batch,role,ids)
                rows,cols=(scores>=self.thresholds[2]).nonzero(as_tuple=True)
                if len(rows):
                    yield from extend(depth+1,torch.cat((batch[rows],ids[cols,None]),-1))
        if len(first):
            yield from extend(1,first[:,None])

    def generate(self,cat,mem,anchors=None):
        dom=Domains(mem)
        for rid,wm in mem.rules.items():
            atoms=cat.atoms[rid]
            if not atoms:
                if anchors is None and (not cat.seminaive[rid] or wm==0):
                    if self.root_scores(cat,mem,rid,None,None,dom).item()>=self.thresholds[0]:
                        yield rid,()
                continue
            for anchor in range(len(atoms) if cat.seminaive[rid] else 1):
                ids=dom.role(cat,mem,rid,anchor,anchor)
                if anchors is not None:
                    forced=anchors.get((rid,anchor),())
                    if forced:
                        first=ints(mem.nodes,sorted(forced))
                        if not torch.isin(first,ids).all():
                            raise ValueError('supplied anchor outside the delta domain')
                    else:
                        continue
                elif len(ids):
                    scores=self.root_scores(cat,mem,rid,anchor,ids,dom)
                    first=ids[scores>=self.thresholds[1]]
                else:
                    continue
                yield from self.expand(cat,mem,dom,rid,anchor,first)

    def decode(self,cat,snapshot,nodes,limit):
        if limit!=1:
            raise ValueError('parallel anchor decoder runs once per sealed Run')
        return list(self.generate(cat,self.memory(cat,snapshot,nodes))),1,'single_batch'

class DisagreementActor(AnchorSetActor):
    """Retain the worst shared-field discrepancy alongside the existing sum of similarities."""
    def __init__(self,vocabulary,names='structural',width=32):
        super().__init__(vocabulary,names,width)
        self.disagreement_scale=nn.Parameter(torch.zeros(()))

    def pair_scores(self,cat,mem,rid,ordered,prefix,role,ids):
        scores,delta=self.pair_components(cat,mem,rid,ordered,prefix,role,ids,measure=True)
        return scores-self.disagreement_scale.clamp_min(0)*delta


class CalibratedAnchorActor(DisagreementActor):
    """Calibrate the issuance decision separately for final and intermediate anchors."""
    def __init__(self,vocabulary,names='structural',width=32):
        super().__init__(vocabulary,names,width)
        self.register_buffer('root_offset',torch.zeros(2))

    def root_scores(self,cat,mem,rid,role,ids,dom):
        score=super().root_scores(cat,mem,rid,role,ids,dom)
        if role is None:
            return score
        return score+self.root_offset[int(len(cat.atoms[rid])>1)]


class FinalParentActor(CalibratedAnchorActor):
    """Score the last named parent from the selected prefix and the candidate port."""
    def __init__(self,vocabulary,names='structural',width=32):
        super().__init__(vocabulary,names,width)
        self.final_query=nn.Linear(3*width,width+1)
        nn.init.zeros_(self.final_query.weight)
        nn.init.zeros_(self.final_query.bias)

    def final_context(self,cat,mem,rid,prefix,role):
        h=mem.keys[prefix].mean(dim=1)
        root=mem.nodes[cat.roots['generated',rid]].expand_as(h)
        atom=mem.nodes[cat.atoms[rid][role][1]].expand_as(h)
        return torch.cat((root,atom,h),dim=-1)

    def final_adjustment(self,context,keys):
        q=self.final_query(context)
        return q[:,:-1] @ keys.T / math.sqrt(self.width) + q[:,-1:]

    def pair_scores(self,cat,mem,rid,ordered,prefix,role,ids):
        scores=super().pair_scores(cat,mem,rid,ordered,prefix,role,ids)
        if len(ordered)+1==len(cat.atoms[rid]):
            scores=scores+self.final_adjustment(self.final_context(cat,mem,rid,prefix,role),mem.keys[ids])
        return scores


class OpaqueParentActor(FinalParentActor):
    """Keep opaque e-class hashes in field comparisons, and scalar fields in port content."""
    catalog_type=TypedContentCatalog

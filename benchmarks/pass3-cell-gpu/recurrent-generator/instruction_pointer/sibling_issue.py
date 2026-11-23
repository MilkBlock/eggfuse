"""Second-batch Cell issuance from a sealed neural frontier and its first named proofs."""
import math
from pathlib import Path

import torch
from torch import nn

from alternate_proofs import digest
from higher_cell import read
from prefix_recovery import bounded_indices


def partitions(priority, cap):
    base = bounded_indices(priority, cap)
    first = bounded_indices(priority, cap // 2)
    is_first = torch.zeros_like(priority,dtype=torch.bool)
    is_first[first] = True
    return first, base[~is_first[base]], (~is_first).nonzero().flatten()


def inputs(cat, mem, rule, points, priority, first):
    rows = mem.keys[points].mean(1)
    root = mem.nodes[cat.roots['generated',rule]].expand_as(rows)
    score = torch.stack((priority.clamp(-1,8), priority.sign(), torch.full_like(priority,math.log1p(len(points)))),1)
    own = torch.cat((root, rows, score),1)
    if not len(first):
        return own, torch.zeros_like(rows), own.new_zeros((len(rows),3))
    # Corresponding positions address the same template atom. Read all its actual
    # columns; unused padding columns from other tables would inflate similarity.
    columns = [mem.fields[points[:,role],:len(mem.ports[j].hashes)] for role,j in enumerate(points[0].tolist())]
    fields = torch.cat(columns,1).flatten(1)
    similarity = (fields @ fields[first].T)/max(fields.size(1),1)
    attended = torch.softmax(similarity*8,1) @ rows[first]
    comparison = torch.stack((similarity.amax(1),similarity.mean(1),torch.ones_like(priority)),1)
    return own, attended, comparison


class SiblingHead(nn.Module):
    def __init__(self,width):
        super().__init__()
        self.own = nn.Linear(2*width+3,24)
        self.context = nn.Linear(width+3,24,bias=False)
        self.output = nn.Linear(24,1)

    def forward(self,own,attended,comparison,with_context):
        h = self.own(own)
        if with_context:
            h = h+self.context(torch.cat((attended,comparison),-1))
        return self.output(h.tanh()).squeeze(-1)


def choose_second(head,features,remaining,base,with_context):
    scores=head(*features,with_context)[remaining]
    pick=bounded_indices(scores,len(base))
    if len(pick)==len(base):
        return remaining[pick],False
    # An unresolved cutoff tie retains the earlier ranking at the same paid budget.
    return base,True


class Allocation:
    def __init__(self,cap,*,folder=None,observe=None,recovery=None):
        if cap<2:
            raise ValueError('two batches need at least two issue slots')
        self.cap=cap
        self.observe=observe
        self.head=None
        self.checkpoint=None
        self.with_context=False
        if folder:
            folder=Path(folder)
            meta=read(folder/'training.json')
            if meta['cap']!=cap or meta['recovery']!=recovery or digest(folder/'head.pt')!=meta['head']:
                raise ValueError('sibling checkpoint differs from calibrated frontier')
            self.checkpoint=meta['head']
            self.with_context=meta['context']
            self.head=SiblingHead(meta['width']).eval()
            self.head.load_state_dict(torch.load(folder/'head.pt',map_location='cpu',weights_only=True))

    def select(self,cat,mem,rule,order,points,priority,count):
        first,base,remaining=partitions(priority,self.cap)
        count['allocation_calls']+=1
        count['allocation_pool']+=len(points)
        count['first_slots']+=len(first)
        count['second_slots']+=len(base)
        chosen=base
        if len(base) and len(remaining)>len(base):
            count['contested_pools']+=1
            features=None
            if self.head is not None or self.observe is not None:
                features=inputs(cat,mem,rule,points,priority,first)
            if self.head is not None:
                chosen,tied=choose_second(self.head,features,remaining,base,self.with_context)
                count['sibling_scores']+=len(remaining)
                count['sibling_boundary_ties']+=int(tied)
                count['different_second_choices']+=int((~torch.isin(chosen,base)).sum())
            if self.observe is not None:
                self.observe(rule,order,points,features,first,base,remaining)
        # Preserve the original neural frontier order for submission/ordinal ties.
        selected=torch.cat((first,chosen)).sort().values
        return points[selected]

    def record(self,counts):
        total=sum(v.get('contested_pools',0) for v in counts.values())
        scored=sum(v.get('sibling_scores',0) for v in counts.values())
        if not total or (self.head is not None and not scored):
            raise ValueError('no contested allocation evaluated')
        return dict(cap=self.cap,first=self.cap//2,context=self.with_context,checkpoint=self.checkpoint,
                    contested=total,scored=scored)

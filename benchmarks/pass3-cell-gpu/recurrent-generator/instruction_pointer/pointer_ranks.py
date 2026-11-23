"""Offline teacher-prefix ranking diagnostics; no scores or labels flow into issuance."""
from collections import Counter

import torch

from actor import ints
from anchor_set import Domains
from train_anchor_set import targets


def ranks(cat,snap,mem,model,labels):
    roots,children=targets(cat,snap,labels)
    dom=Domains(mem)
    totals={'anchor':Counter(),'parent':Counter()}

    def add(level,scores,ids,positive,cut):
        y=torch.isin(ids,ints(ids,sorted(positive)))
        if int(y.sum())!=len(positive): raise ValueError('target excluded by pointer domain')
        n=len(positive)
        # Fractional credit at a tie avoids giving the model the teacher's port order.
        boundary=scores.topk(n).values[-1]
        above=scores>boundary
        same=scores==boundary
        credit=float(y[above].sum())+(n-int(above.sum()))*float(y[same].sum())/int(same.sum())
        on=scores>=cut
        totals[level].update(reads=1,candidates=len(ids),required=n,passing=int(on.sum()),
                             hits=int(y[on].sum()),credit_at_teacher_k=credit,
                             positive_logit_sum=float(scores[y].sum()))
    for (rid,anchor),pos in roots.items():
        if anchor is None: continue
        ids=dom.role(cat,mem,rid,anchor,anchor)
        add('anchor',model.root_scores(cat,mem,rid,anchor,ids,dom),ids,pos,model.thresholds[1])
    for (rid,anchor,prefix),pos in children.items():
        order=[anchor]+[j for j in range(len(cat.atoms[rid])) if j!=anchor]
        role=order[len(prefix)]
        ids=dom.role(cat,mem,rid,anchor,role)
        scores=model.pair_scores(cat,mem,rid,order[:len(prefix)],ints(mem.nodes,[prefix]),role,ids)[0]
        add('parent',scores,ids,pos,model.thresholds[2])
    return totals

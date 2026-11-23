"""Count new distinct reference commits from second-batch choices on identical named frontiers."""
import argparse
import json
from collections import Counter
from pathlib import Path

import torch

from alternate_proofs import digest
from higher_cell import read
from sibling_issue import Allocation,choose_second


@torch.no_grad()
def audit(data,models,name):
    manifest=read(data/(name+'.json'))
    path=data/(name+'.pt')
    if manifest['split']!='validation' or digest(path)!=manifest['data']:
        raise ValueError('expected a whole-program validation file')
    rows=torch.load(path,weights_only=True)
    results={}
    for arm in ('plain','blind','context','masked'):
        head=None
        if arm!='plain':
            model=models/('context' if arm=='masked' else arm)
            head=Allocation(manifest['cap'],folder=model,recovery=manifest['recovery'])
        first_hits=set()
        second_hits=set()
        available=set()
        counts=Counter()
        for row in rows:
            y=row['y']
            base=row['base']
            chosen=base
            if head is not None:
                chosen,tied=choose_second(head.head,row['x'],row['remaining'],base,arm=='context')
                counts['boundary_ties']+=int(tied)
            if len(chosen)!=len(base):
                raise ValueError('unequal number of issued proposals')
            counts['first_paid']+=len(row['first'])
            counts['second_paid']+=len(chosen)
            first_hits.update(y[row['first']].tolist())
            second_hits.update(y[chosen].tolist())
            available.update(y.tolist())
        first_hits.discard(0);second_hits.discard(0);available.discard(0)
        results[arm]=dict(counts=counts,first=len(first_hits),second_new=len(second_hits-first_hits),
                          distinct=len(first_hits|second_hits),reachable=len(available))
    return dict(mode='contested root pools on teacher snapshots',
                corpus=manifest,results=results)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('name')
    for k in ('data','models','out'):p.add_argument(k,type=Path)
    a=p.parse_args()
    torch.set_num_threads(1)
    a.out.write_text(json.dumps(audit(a.data,a.models,a.name),indent=2)+'\n')

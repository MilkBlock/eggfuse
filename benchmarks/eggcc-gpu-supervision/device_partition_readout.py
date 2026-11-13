"""Bake a bounded legal Eq-state catalog; score it on GPU without graph walks.

Legality is not truth. Selection never authorizes union or ownership transfer.
"""
from collections import defaultdict
from itertools import product
import numpy as np


def partitions(n):
    if n==0:return [()]
    rows=[(0,)]
    for _ in range(1,n):rows=[p+(k,) for p in rows for k in range(max(p)+2)]
    return rows


def compile_catalog(rule,row,max_classes=5,max_states=256):
    parent={a:a for pair in row['pairs'] for a in pair}
    def root(a):
        while parent[a]!=a:a=parent[a]
        return a
    for (a,b),yes in zip(row['pairs'],row['static']):
        if yes:parent[root(b)]=root(a)
    groups=defaultdict(list)
    for a in sorted(set(root(a) for a in parent)):
        groups[rule['slots'][a]['sort']['name']].append(a)
    if any(len(g)>max_classes for g in groups.values()):return dict(covered=False,reason='class_budget')
    choices=[partitions(len(g)) for g in groups.values()]
    count=1
    for c in choices:count*=len(c)
    if count>max_states:return dict(covered=False,reason='state_budget')
    representatives=row['quotient']['representatives'];candidates=[]
    for choice in product(*choices):
        labels={a:(sort,c) for (sort,g),labels in zip(groups.items(),choice) for a,c in zip(g,labels)}
        candidates.append(tuple(labels[root(row['pairs'][i][0])]==labels[root(row['pairs'][i][1])] for i in representatives))
    # Ties prefer fewer equalities, but remain marked ambiguous.
    candidates=sorted(set(candidates),key=lambda v:(sum(v),v))
    matrix=np.array(candidates,np.float32).reshape(len(candidates),len(representatives))
    return dict(covered=True,matrix=matrix,classes=sum(map(len,groups.values())),states=len(matrix))


def select(scores,matrix,xp):
    if scores.shape[-1]!=matrix.shape[-1] or matrix.shape[0]<1:raise ValueError('partition layout mismatch')
    finite=xp.all(xp.isfinite(scores),axis=-1)
    clean=xp.where(xp.isfinite(scores),scores,0)
    energy=(1-2*clean)@xp.swapaxes(matrix,-1,-2)
    finite=finite&xp.all(xp.isfinite(energy),axis=-1)
    energy=xp.where(xp.isfinite(energy),energy,0)
    winner=xp.argmin(energy,axis=-1)
    ordered=xp.sort(energy,axis=-1)
    gap=ordered[...,1]-ordered[...,0] if matrix.shape[0]>1 else xp.full(scores.shape[:-1],float('inf'))
    ambiguous=gap<=1e-6
    return matrix[winner],dict(ready=finite&~ambiguous,ambiguous=ambiguous,nonfinite=~finite,gap=gap)

"""Offline fresh structural acceptance and exact functional-graph signatures."""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from task import generate
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'depth'))
from probe import inputs


def successor(a,b):
    keys={int(row[0]):i for i,row in enumerate(a)};edges={int(row[0]):int(row[1]) for row in b}
    return [keys[edges[int(row[0])]] for row in a]


def signature(succ):
    n=len(succ);incoming=[[] for _ in range(n)];degree=[0]*n
    for i,j in enumerate(succ):incoming[j].append(i);degree[j]+=1
    queue=[i for i,v in enumerate(degree) if v==0];removed=set(queue)
    for i in queue:
        j=succ[i];degree[j]-=1
        if degree[j]==0:queue.append(j);removed.add(j)
    cyclic=set(range(n))-removed
    def tree(i):return '('+''.join(sorted(tree(k) for k in incoming[i] if k not in cyclic))+')'
    seen=set();components=[]
    for i in sorted(cyclic):
        if i in seen:continue
        cycle=[];j=i
        while j not in seen:seen.add(j);cycle.append(tree(j));j=succ[j]
        rotations=[tuple(cycle[k:]+cycle[:k]) for k in range(len(cycle))]
        components.append(min(rotations))
    return repr(tuple(sorted(components)))


def fresh(rows,length,count,seed,family):
    d=generate(rows,length,count,seed,'functional');rng=np.random.default_rng(seed+29);n=rows*length
    for g in range(count):
        order=rng.permutation(d['a'][g,:,0]);edges={}
        if family=='two_tails':
            for chain in (order[:n//2],order[n//2:]):
                for i,key in enumerate(chain):edges[int(key)]=int(chain[min(i+1,len(chain)-1)])
        elif family=='two_cycle_tail':
            for i,key in enumerate(order):edges[int(key)]=int(order[i+1] if i+1<n else order[-2])
        else:raise ValueError(family)
        d['b'][g,:,1]=[edges[int(key)] for key in d['b'][g,:,0]]
    d['x_a'],d['x_b']=inputs(d['a'],d['b']);d['family']=family
    for k in ('targets','fields','cycle_keys'):d.pop(k,None)
    return d

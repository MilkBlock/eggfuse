"""Static independent source-witness plans. Rule order/inputs only; no runtime RHS or labels."""
from itertools import permutations
import argparse
import json
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'coverage-target'))
from addressability import minimum_witnesses


def compile_plan(q,anchors):
    # Explore only reorderings of the source-independent anchors already proved
    # sufficient by the common FD analysis. Closed suffixes are exact point reads.
    best=None
    orders=permutations(anchors) if len(anchors)<=5 else [anchors]
    for seq in orders:
        bound=set();done=set();instructions=[];links=[]
        def close():
            while True:
                changed=False
                for j,(op,args) in enumerate(q):
                    if j in done or j in set(seq):continue
                    if all(slot<0 or slot in bound for slot in args[:-1]):
                        instructions.append([j,0,[]]);done.add(j);bound.update(v for v in args if v>=0);changed=True
                if not changed:break
        close()
        for anchor in seq:
            op,args=q[anchor]
            shared=[col for col,slot in enumerate(args) if slot>=0 and slot in bound]
            instructions.append([anchor,1,shared]);links.append(len(shared));done.add(anchor)
            bound.update(v for v in args if v>=0);close()
        if len(done)!=len(q):continue
        rank=(sum(v>0 for v in links[1:]),sum(links),tuple(links[1:]),tuple(-i for i in seq))
        if best is None or rank>best[0]:best=(rank,instructions,links)
    if best is None:raise ValueError(('closure plan failed',q,anchors))
    # A minimum witness set can have no shared columns: Get and TupleT
    # independently determine the HasType lookup. Offering the bridge HasType
    # row as an additional pointer connects both learned choices.
    if not all(best[2][1:]):
        for first,(op,_) in enumerate(q):
            if not isinstance(op,int):continue
            bound=set();done=set();ins=[];links=[]
            while len(done)<len(q):
                ready=[i for i,(_,args) in enumerate(q) if i not in done and all(v<0 or v in bound for v in args[:-1])]
                rel=[i for i,(op,_) in enumerate(q) if i not in done and isinstance(op,int)]
                if ready:i=ready[0];pick=0
                elif not rel:break
                else:
                    i=first if not links and first in rel else max(rel,key=lambda j:sum(v>=0 and v in bound for v in q[j][1]))
                    pick=1
                shared=[col for col,v in enumerate(q[i][1]) if v>=0 and v in bound] if pick else []
                if pick:links.append(len(shared))
                ins.append([i,pick,shared]);done.add(i);bound.update(v for v in q[i][1] if v>=0)
            if len(done)==len(q) and len(links)>=2 and all(links[1:]):
                if not all(best[2][1:]) or len(links)<len(best[2]):best=(None,ins,links)
    return best[1:]


def compile_program(image):
    p=json.loads((image/'ingress.json').read_text());plans=[]
    primitives={op for r in p['rules'] for op,_ in r['q'] if isinstance(op,str)}
    for r in p['rules']:
        anchors=minimum_witnesses(r,primitives)
        if len(anchors)<2:plans.append(None);continue
        ins,linked=compile_plan(r['q'],anchors)
        plans.append(dict(width=len(anchors),ins=ins,linked=linked))
    return plans

def sealed_plans(image):
    """Name every independent source before any point lookup or exact unification."""
    from collections import deque
    packet=json.loads((image/'ingress.json').read_bytes());base=compile_program(image)
    for rid,(r,prior) in enumerate(zip(packet['rules'],base)):
        if not prior:continue
        q=r['q'];rels=[i for i,(op,_) in enumerate(q) if isinstance(op,int)]
        def slots(xs):return frozenset(v for v in xs if v>=0)
        keys=[slots(args[:-1]) for _,args in q];fields=[slots(args) for _,args in q]
        queue=deque((fields[i],(i,)) for i in rels);seen={s for s,_ in queue}
        determined=None
        while queue:
            bound,path=queue.popleft()
            closure=bound;done=set(path);suffix=[]
            while True:
                old=len(done)
                for j in range(len(q)):
                    if j not in done and keys[j]<=closure:
                        done.add(j);suffix.append((j,0,[]));closure=closure|fields[j]
                if old==len(done):break
            if len(done)==len(q):
                determined=(path,suffix);break
            for j in rels:
                if fields[j]&bound and fields[j]-bound:
                    nbound=bound|fields[j]
                    if nbound not in seen:seen.add(nbound);queue.append((nbound,(*path,j)))
        if determined is None:
            base[rid]=None;continue
        path,suffix=determined;bound=set();ins=[];linked=[]
        for i in path:
            cols=[k for k,v in enumerate(q[i][1]) if v in bound]
            ins.append((i,1,cols));bound.update(fields[i]);linked.append(len(cols))
        assert len(path)>=prior['width'] and all(linked[1:])
        base[rid]=dict(width=prior['width'],ins=ins+suffix,linked=linked)
    return base


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('image',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--sealed',action='store_true')
    a=p.parse_args()
    fn=sealed_plans if a.sealed else compile_program
    a.output.write_text(json.dumps(fn(a.image),separators=(',',':'))+'\n')

"""Small scheduled two-Cell episodes for gate pretraining. No native timing labels."""
import json
from pathlib import Path
import random

LIBRARY=Path(__file__).resolve().parents[1]/'higher-order-bake'
FAMILY=json.loads((LIBRARY/'catalog.json').read_bytes())['family']
INTERFACES=tuple(tuple(v) for v in json.loads((LIBRARY/'growth.json').read_bytes())['second_round'])
THRESHOLD=FAMILY['threshold']
RECURSIVE=FAMILY['gt']


def ports(producer,effect,value,depth):
    return [1.,(producer%64)/63,min(effect,15)/15,max(-32,min(32,value))/32,
            min(depth,16)/16,float(value==THRESHOLD),float(value>THRESHOLD),float(depth>1)]


def replay(publications, events):
    """Visit the current generation, check the branch, then credit a distinct physical result once."""
    live={};won=set();rows=[dict(p,counts=[0,0,0,0]) for p in publications]
    dirty=False; watermarks={1:0,2:0}; external_reads=0
    for event in events:
        op,arg,epoch=event
        if op=='publish':
            p=rows[arg];live[p['address']]=arg;dirty=True
        elif op=='invalidate':
            live.pop(arg,None);dirty=True
        elif op=='read':
            # The intermediate still exists as a visible source port. A saved node receives no credit.
            external_reads+=int(arg in live)
        else:
            assert op=='consumer' and arg in (1,2)
            if dirty:
                for idx in live.values():rows[idx]['counts'][3]+=1
                dirty=False
            for idx in live.values():
                p=rows[idx];v=p['value'];branch=2 if v>THRESHOLD else 1 if v==THRESHOLD else 0
                c=p['counts'];c[0]+=1
                if arg==branch and p['epoch']>=watermarks[arg]:
                    c[1]+=1
                    key=(p['result'],p['value'],arg)
                    if key not in won:
                        c[2]+=1;won.add(key)
            watermarks[arg]=epoch
    return rows,external_reads


def sample(seed, episodes):
    rng=random.Random(seed);result=[]
    for _ in range(episodes):
        parents=[];events=[];ready=[];epochs=rng.randrange(2,8)
        for epoch in range(1,epochs+1):
            if parents:
                observed,_=replay(parents,events)
                ready=[p for p in observed if p['counts'][2] and p['value']>THRESHOLD and not p.get('used')]
            for _ in range(rng.randrange(1,6)):
                producer,effect=rng.choice(INTERFACES);addr=rng.randrange(8)
                if producer==RECURSIVE and ready:
                    prev=ready.pop(rng.randrange(len(ready)))
                    parents[prev['id']]['used']=True
                    value,depth=prev['value']-1,prev['depth']+1
                else:
                    value=rng.randrange(THRESHOLD if producer==RECURSIVE else THRESHOLD-1,THRESHOLD+9);depth=1
                parents.append(dict(id=len(parents),address=addr,result=rng.randrange(8),epoch=epoch,value=value,depth=depth,
                                    features=ports(producer,effect,value,depth)))
                events.append(('publish',len(parents)-1,epoch))
                if rng.random()<.25:events.append(('read',addr,epoch))
                if rng.random()<.18:events.append(('invalidate',addr,epoch))
            for branch in (1,2):
                if rng.random()<.78:events.append(('consumer',branch,epoch))
        rows,_=replay(parents,events)
        result.extend(rows)
    return result


def check():
    base=dict(address=4,result=9,epoch=1,value=2,features=ports(*INTERFACES[0],2,1))
    a,b,c=base,dict(base,address=5),dict(base,value=1,epoch=2)
    rows,readers=replay([a,b,c],[('publish',0,1),('publish',1,1),('read',4,1),('consumer',2,1),
                                 ('publish',2,2),('invalidate',4,2),('consumer',1,2)])
    assert readers==1 and [r['counts'][2] for r in rows]==[1,0,0]
    rows,_=replay([a,c],[('publish',0,1),('publish',1,2),('consumer',1,2)])
    assert [r['counts'][2] for r in rows]==[0,1]

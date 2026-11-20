"""Mine producer/request interfaces in train-only Pass 3 publications and their realized continuations."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import sys
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'verifier-placement'))
from transactions import collect


def read(p):return json.loads(p.read_bytes())


def bake(corpus,captures,out):
    runs=read(corpus/'collection.json')
    groups=defaultdict(lambda:defaultdict(Counter))
    for name,info in runs.items():
        if info['split']!='train':continue
        img=corpus/name/'input'
        events,contracts=collect(img,captures/name)
        if len(contracts)!=1:raise ValueError('ambiguous branch pair')
        table,col,threshold,eq,gt=contracts[0]
        with np.load(captures/name/'neural-inputs.npz') as obs,np.load(captures/name/'output.npz') as graph:
            tickets=obs['consumed'];rhs=graph['rhs'];pub=obs['publications']
        reached=defaultdict(set)
        for ordinal in np.flatnonzero(tickets):reached[int(tickets[ordinal])].add(int(rhs[ordinal,1]))
        for run,ticket,rule,effect,row,value,k,branch,constant,_,_ in events:
            key=(table,col,threshold,eq,gt,int(rule),int(effect))
            c=groups[key][name];c['publications']+=1;c['literal']+=int(constant)
            c[f'guard_{branch}']+=1
            if (eq if branch==1 else gt if branch==2 else -1) in reached[ticket]:
                c[f'consumed_{branch}']+=1
            parent=int(pub[ticket-1,0])-1
            grand=int(tickets[parent])
            if grand:
                prior,prior_effect,_,_=pub[grand-1]
                if (rhs[prior-1,1],prior_effect)==(rule,effect):c['self_predecessor']+=1
    candidates=[]
    for key,cases in groups.items():
        support=sorted(n for n,c in cases.items() if c['consumed_1'] and c['consumed_2'] and c['literal']<c['publications'])
        c=sum(cases.values(),Counter())
        candidates.append(dict(interface=key,programs=cases,dynamic_support=support,events=c,
                               realized=c['consumed_1']+c['consumed_2']))
    ranked=sorted((v for v in candidates if len(v['dynamic_support'])>=2),key=lambda v:(-v['realized'],v['interface']))
    if not ranked:raise ValueError('no dynamic learned interface')
    first=ranked[0];t,col,k,eq,gt,r,e=first['interface']
    result=dict(schema='eggfuse.guard-catalog/v1',training=[n for n,x in runs.items() if x['split']=='train'],
                family=dict(table=t,column=col,threshold=k,eq=eq,gt=gt),
                first=[r,e],seed_support=first['programs'],opportunities=candidates)
    out.write_text(json.dumps(result,indent=1)+'\n')
    print(result['first'],result['seed_support'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for s in ('corpus','captures','out'):p.add_argument(s,type=Path)
    a=p.parse_args();bake(a.corpus,a.captures,a.out)

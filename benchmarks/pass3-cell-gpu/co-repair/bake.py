"""Build fixed-budget libraries from training families only. No reader pairing uses future events."""
from collections import Counter,defaultdict
import json
import numpy as np
from collect import read
from device import files


class Trace:
    def __init__(self,root,reference,profiles,name):
        image,_,_=files(root,reference,name)
        schemas=read(image/'ingress.json')['tables']
        with np.load(profiles/name/'output.npz') as graph:
            tids=graph['meta'][:,0].tolist()
            self.row_counts=graph['unions'][:,1].tolist()
        self.options=defaultdict(list)
        self.frequency=Counter()
        self.continuation=Counter()
        self.joint=Counter()
        self.boundary=Counter()
        with np.load(profiles/name/'co-repair.npz') as z:
            matrix=z['edges']
            for row,col in zip(*np.nonzero(matrix)):
                row,col=int(row),int(col)
                code=int(matrix[row,col]);donor=abs(code)-1
                key=(schemas[tids[donor]]['name'],schemas[tids[row]]['name'],col)
                assert donor<row and schemas[tids[donor]]['schema'][-1]==schemas[tids[row]]['schema'][col]
                self.options[row].append((donor,key))
                self.frequency[key]+=1
                self.continuation[key]+=code<0
            self.events=[{} for _ in self.row_counts]
            for event,row,mask in z['events'].tolist():
                assert row not in self.events[event] and row<self.row_counts[event]
                self.events[event][row]=mask
        by_donor=defaultdict(list)
        for reader,options in self.options.items():
            for donor,key in options:by_donor[donor].append((reader,key))
        for count,woken in zip(self.row_counts,self.events):
            for donor,fields in woken.items():
                if not fields & (1<<(len(schemas[tids[donor]]['schema'])-1)):continue
                for reader,key in by_donor[donor]:
                    if reader>=count:continue
                    if woken.get(reader,0) & (1<<key[2]):
                        self.joint[key]+=1
                    else:
                        self.boundary[key]+=1

    def group(self,library,members):
        rank={k:i for i,k in enumerate(library)}
        owner={};children=defaultdict(list)
        for row,options in self.options.items():
            candidates=[(rank[k],donor) for donor,k in options if k in rank
                        and donor not in owner and len(children.get(donor,()))<members-1]
            if candidates:
                _,donor=min(candidates)
                owner[row]=donor
                children[donor].append(row)
        saved=extra=total=0
        for limit,woken in zip(self.row_counts,self.events):
            owners={owner.get(w,w) for w in woken}
            saved+=len(woken)-len(owners)
            total+=len(woken)
            # Upper bound on the live members of an instance-only subscriber:
            # strict physical addresses remain valid across tombstones.
            for o in owners:
                if o in children:
                    extra+=int(o not in woken)+sum(c<limit and c not in woken for c in children[o])
        return dict(attached=len(owner),instances=len(children),work=total,
                    joint_notifications_saved=saved,member_overwake_bound=extra)


def candidates(traces,budget):
    frequency,continuation,joint,boundary=(Counter() for _ in range(4))
    for trace in traces:
        for counts,observed in [(frequency,trace.frequency),(continuation,trace.continuation),
                                (joint,trace.joint),(boundary,trace.boundary)]:
            counts.update(observed)
    pool=[k for k in frequency if sum(t.frequency[k]>0 for t in traces)>=2]
    if len(pool)<budget:raise ValueError('insufficient supported shapes')
    # Identical candidate set, descriptor width, and budget for every ranking.
    # Break a tie with the static shape, never with evaluation trace counts.
    def top(score):return sorted(pool,key=lambda k:(-score(k),k))[:budget]
    arms={'continuation':top(lambda k:continuation[k]),'joint':top(lambda k:joint[k])}
    for scale in (0.25,1,4):
        arms[f'penalty-{scale}']=top(lambda k:joint[k]-scale*boundary[k])
    metadata={'pool':len(pool),'positive_spine_shapes':sum(continuation[k]>0 for k in pool),
              'positive_joint_shapes':sum(joint[k]>0 for k in pool)}
    return arms,metadata

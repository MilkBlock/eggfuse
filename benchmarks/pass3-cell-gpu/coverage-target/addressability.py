"""Count source RHS occurrences by the smallest independently proposed tuple of relation witnesses."""
import argparse
from collections import Counter,deque
import json
from pathlib import Path


def slots(args):
    return sum(1<<s for s in set(args) if s>=0)


def minimum_witnesses(rule,primitives):
    """Use only functional table keys and forward primitive evaluation; no inverse or hindsight uniqueness."""
    query=rule['q']
    inputs=[slots(args[:-1]) for _,args in query]
    outputs=[slots(args) for _,args in query]
    rel=[i for i,(op,_) in enumerate(query) if isinstance(op,int)]
    if not all(isinstance(op,int) or op in primitives for op,_ in query):
        raise ValueError('unknown primitive in active rule')
    def close(bound):
        while True:
            before=bound
            for key,variables in zip(inputs,outputs):
                if not key & ~bound:bound|=variables
            if before==bound:return bound
    goal=slots([v for _,args in query for v in args])
    start=close(0)
    queue=deque([(start,())]);seen={start}
    while queue:
        current,witnesses=queue.popleft()
        if current==goal:
            return witnesses
        for i in rel:
            if not outputs[i]&~current:continue
            nxt=close(current|outputs[i])
            if nxt not in seen:
                seen.add(nxt);queue.append((nxt,(*witnesses,i)))
    raise ValueError('unsupported unbound primitive inputs')


def read_json(p):
    return json.loads(p.read_text())


def study(image,source,trace,primitives):
    import numpy as np
    p=read_json(image/'ingress.json')
    rules=p['rules'];meta=read_json(source)['recipe']['rules']
    with np.load(trace/'output.npz') as z:
        rhs=z['rhs'];runs=z['runs'];resumes=z['resumes']
    assert len(rhs)==runs[:,1].sum()
    per_rule=Counter(map(int,rhs[:,1]))
    widths={};buckets=Counter();rows=[]
    for i,num in per_rule.items():
        rule=rules[i];witnesses=minimum_witnesses(rule,primitives);width=len(witnesses)
        widths[i]=width;buckets[width]+=num
        rows.append(dict(id=i,source_set=meta[i]['metadata']['source_set'],committed=num,witnesses=list(witnesses),
                         anchor_tables=[p['tables'][rule['q'][w][0]]['name'] for w in witnesses],
                         atoms=len(rule['q']),relations=sum(isinstance(op,int) for op,_ in rule['q'])))
    assert sum(buckets.values())==len(rhs)
    # Cross-check the accounting at each scheduled Run and allow no credit for static roots.
    prefix=runs[:,1].cumsum()-runs[:,1]
    spine=set()
    for run,local,*_ in resumes:
        ordinal=int(prefix[run-1]+local-1)
        assert 0<=ordinal<len(rhs) and rhs[ordinal,0]==run and ordinal not in spine
        spine.add(ordinal)
    by_origin={name:Counter() for name in ('spine','ordinary')}
    for i,r in enumerate(rhs):by_origin['spine' if i in spine else 'ordinary'][widths[int(r[1])]]+=1
    target=(98*len(rhs)+99)//100
    budgets=[1,2,4,8,16,32,64,128,256,512,1024]
    emitted={k:int(np.minimum(k,runs[:,1]).sum()) for k in budgets}
    min_fixed=next(k for k in range(1,int(max(runs[:,1]))+1) if int(np.minimum(k,runs[:,1]).sum())>=target)
    return dict(rhs=len(rhs),runs=len(runs),target=target,max_exact_fallback=len(rhs)-target,
                by_minimum_witnesses=dict(sorted(buckets.items())),by_source=by_origin,
                bound_if_only_zero_and_one=sum(n for k,n in buckets.items() if k<=1),
                required_multi_at_98=max(target-sum(n for k,n in buckets.items() if k<=1),0),
                single_rhs_per_token_ceilings=emitted,min_fixed_slots_for_98=min_fixed,
                max_run_rhs=int(max(runs[:,1])),rules=sorted(rows,key=lambda r:(-r['committed'],r['id'])))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for k in ('ref','corpus','out'):ap.add_argument(k,type=Path)
    args=ap.parse_args()
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from lower import OPCODES
    results={}
    for name in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax'):
        if name in ('sum-bits','dot-product'):
            image,program,trace=args.ref/f'release-input-{name}',args.ref/name/'program.json',args.ref/f'release-{name}'
        else:
            base=args.corpus/name;image,program,trace=base/'input',base/'program.json',base/'device'
        results[name]=study(image,program,trace,OPCODES)
    args.out.write_text(json.dumps(results,indent=1)+'\n')
    for n,d in results.items():print(n,d['target'],d['by_minimum_witnesses'],d['by_source'],d['min_fixed_slots_for_98'])

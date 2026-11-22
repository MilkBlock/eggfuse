"""Score rule 144 proposals at native snapshots, with causal self-result feedback."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from joined_port_policy import fit


def fields(role, raw):
    if raw is None or any(v is None for v in raw):
        return None
    if role == 0:
        expr, start, length, result = raw
        def integer(v):
            return v["Int"] if isinstance(v,dict) else v
        return expr["Eq"], integer(start), integer(length), result["Eq"]
    left,right,result = raw
    return left["Eq"],right["Eq"],result["Eq"]


def fit_address(correlated=False):
    """Learn three field selections from generated matched rows without EggCC labels."""
    import torch
    gen=torch.Generator().manual_seed(144)
    base,start,length,left,right=torch.randint(10000,(5,512),generator=gen)
    if correlated:
        start=base
        length=torch.zeros_like(base)
        right=left
    sources=torch.stack((base,start,length,start+length,left,right),dim=1)
    observed=torch.stack((base,start+length,right),dim=1)
    equal=(sources[:,None,:]==observed[:,:,None])
    scores=torch.nn.Parameter(torch.zeros(3,6))
    opt=torch.optim.Adam([scores],lr=.1)
    for _ in range(40):
        opt.zero_grad()
        loss=-scores.log_softmax(-1).expand_as(equal).masked_fill(~equal,-torch.inf).logsumexp(-1).mean()
        loss.backward()
        opt.step()
    return scores.detach().argmax(-1).tolist()


def replay(trace, head, feedback, route=None, transfers=False, delta_route=False):
    if trace['tables'] != ['SubTuple',None,'SubTuple','Concat']:
        raise ValueError("unexpected scalar template")
    by_epoch = defaultdict(list)
    commits = defaultdict(dict)
    for e in trace['events']:
        by_epoch[e[0]].append(e)
    for epoch,owner,refs in trace['commits']:
        r=dict(refs)
        if set(r)!={0,2}:
            raise ValueError("unexpected source signature")
        commits[epoch][owner]=(tuple(r[0]),tuple(r[2]))
    schedule=dict(trace['schedule'])
    if set(commits)-set(schedule):
        raise ValueError("missing scheduled Run")
    ports={0:{},3:{}}
    links=defaultdict(list)
    if transfers:
        for ep,hi,lo in trace['aliases']:
            links[ep].append((hi,lo))
    parents={}
    def root(x):
        while x in parents:
            x=parents[x]
        return x
    counts=Counter()
    retired=set()
    completed=set()
    origins=Counter()
    seen=set()
    weights,bias=head
    # Precompute the eight outputs of the trained threshold on finite features.
    from itertools import product
    verdict={bits:sum(w*b for w,b in zip(weights,bits))+bias>0 for bits in product((False,True),repeat=3)}
    for ep in sorted(set(schedule)|set(by_epoch)|set(links)):
        if ep in schedule:
            mark=schedule[ep]
            sub=defaultdict(list)
            addressed=defaultdict(list)
            fresh_sub=defaultdict(list)
            fresh_addresses=defaultdict(list)
            for addr,raw in ports[0].values():
                v=(root(raw[0]),raw[1],raw[2],root(raw[3]))
                sub[v[3]].append((addr,v))
                if route is not None:
                    address=v[0],v[1],v[3]
                    addressed[address].append((addr,v))
                    if delta_route and addr[-1]>=mark:
                        fresh_sub[v[3]].append((addr,v))
                        fresh_addresses[address].append((addr,v))
            pairs=set()
            for concat,(left,right,_) in ports[3].values():
                left,right=root(left),root(right)
                left_bank=fresh_sub if delta_route and concat[-1]<mark and right not in fresh_sub else sub
                for a,(expr,start,length,_) in left_bank.get(left,()):
                    end=start+length
                    candidates=sub.get(right,())
                    if route is not None:
                        sources=(expr,start,length,end,left,right)
                        right_bank=fresh_addresses if delta_route and max(a[-1],concat[-1])<mark else addressed
                        candidates=right_bank.get(tuple(sources[i] for i in route),())
                        counts['conditional_reads']+=1
                    for b,(other,offset,_,result_id) in candidates:
                        counts['pair_scores']+=1
                        bits=(expr==other, -(1<<63)<=end<1<<63 and end==offset,
                              max(a[-1],b[-1],concat[-1])>=mark)
                        if verdict[bits] and result_id==right:
                            pairs.add((a,b))
            labels=set(commits[ep].values())
            if len(labels)!=len(commits[ep]):
                raise ValueError("two source commits have identical independent parents")
            known={addr:values for addr,values in ports[0].values()}
            concats={(root(v[0]),root(v[1])) for _,v in ports[3].values()}
            owners={pair:owner for owner,pair in commits[ep].items()}
            for a,b in labels-pairs:
                if a not in known or b not in known:
                    counts['missing_subtuple']+=1
                elif (root(known[a][3]),root(known[b][3])) not in concats:
                    counts['missing_concat']+=1
                    proof=trace.get('proof',{}).get(str(owners[a,b]),())
                    for atom,raw,_,allocator in proof:
                        if atom==3:
                            addr=tuple(raw)
                            row=ports[3].get(addr[:-1])
                            cause=('never_seen' if addr[:-1] not in seen else
                                   'withdrawn' if not row else
                                   'different_version' if row[0]!=addr else 'different_fields')
                            origins[f'{allocator}/{cause}']+=1
                else:
                    counts['failed_guard_or_watermark']+=1
            completed.update(owner for owner,pair in commits[ep].items() if pair in pairs)
            counts.update(runs=1,expected=len(labels),issued=len(pairs),missing=len(labels-pairs),extra=len(pairs-labels))
        for hi,lo in links[ep]:
            parents[hi]=lo
        for _,owner,slot,role,raw,values,kind in sorted(by_epoch[ep],key=lambda e:(e[-1] in ('retire','revision'),e[1],e[2])):
            addr=tuple(raw)
            key=addr[:-1]
            bank=ports[role]
            old=bank.get(key)
            if kind=='self' and (not feedback or owner not in completed):
                continue
            if kind=='revision' and not old:
                continue
            if old and old[0][-1]>addr[-1]:
                continue
            if kind=='retire':
                retired.add(addr)
                bank.pop(key,None)
                continue
            vals=fields(role,values)
            if vals is not None and addr not in retired:
                bank[key]=(addr,vals)
                seen.add(key)
                if kind=='self':
                    counts['own_returns']+=1
    return dict(counts,concat_origins=dict(origins))


if __name__=='__main__':
    import torch
    torch.set_num_threads(1)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('traces',nargs='+',type=Path)
    args=parser.parse_args()
    w,b=fit(3,lambda same,adjacent,fresh:same and adjacent and fresh)
    head=w.tolist(),b.item()
    router=fit_address()
    control=fit_address(correlated=True)
    output=dict(routes=dict(varied=router,correlated=control))
    for p in args.traces:
        trace=json.loads(p.read_text())
        output[p.stem]={k:replay(trace,head,mode,route) for k,mode,route in (
            ('independent',False,None),('feedback',True,None),('conditional',True,router),
            ('correlated',True,control))}
        if trace.get('aliases'):
            ordinary=output[p.stem]['conditional_with_transfers']=replay(trace,head,True,router,True)
            routed=output[p.stem]['delta_routed']=replay(trace,head,True,router,True,True)
            for k in ('expected','issued','missing','extra'):
                if ordinary[k]!=routed[k]:
                    raise ValueError((p,k,"delta route changed bindings"))
        for key in ('expected','issued','missing','extra'):
            if output[p.stem]['feedback'][key]!=output[p.stem]['conditional'][key]:
                raise ValueError((p,key,"conditional reader changed reference coverage"))
    print(json.dumps(output,indent=2))

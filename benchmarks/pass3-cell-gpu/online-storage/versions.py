"""Post-execution permission tiers for citing actual prior published rows. Never credited to a neural model."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path


def freeze(v):
    if isinstance(v,dict):return tuple((k,freeze(x)) for k,x in sorted(v.items()))
    if isinstance(v,list):return tuple(map(freeze,v))
    return v


def measure(folder,extra=None,mutable=None):
    read=lambda p:json.loads((folder/p).read_bytes())
    records=read('references.json');events=read('audit.json')['events']
    calls=records['effects'];rhs=records['lhs'];by_run=defaultdict(list)
    for ordinal,outputs in (extra or {}).items():calls[ordinal-1][3].extend(outputs)
    for idx,item in enumerate(rhs,1):by_run[item[0]].append(idx)
    uf={}
    def representative(p):
        while p in uf:
            if uf[p] in uf:uf[p]=uf[uf[p]]
            p=uf[p]
        return p
    def canonical(x):
        if not isinstance(x,tuple):return x
        if len(x)==1 and isinstance(x[0],tuple) and len(x[0])==2 and x[0][0]=='Eq':
            return (('Eq',representative(x[0][1])),)
        return tuple(map(canonical,x))
    def is_set(value):return 'Set' in repr(value)
    # id 0 is an original input fact and has no prior neural action.
    history=defaultdict(list);tables=defaultdict(set);last_write={};latest_effect={}
    for t,a,v,fields in records['initial']:
        a=tuple(a);history[a].append((0,v,t,freeze(fields),-1));tables[t].add(a)
    counts=defaultdict(Counter);depths=defaultdict(dict);examples={};missing=defaultdict(Counter)
    for tick,run_events in enumerate(events,1):
        ids=by_run[tick]
        # Build canonical lookup for all observed historical row versions only when a current address lacks support.
        by_tuple={}
        def alternatives(t,row):
            if t not in by_tuple:
                index=defaultdict(list)
                for old in tables[t]:
                    for prior,_,table,values,op in history[old]:
                        if table==t:index[canonical(values)].append((prior,old,op))
                by_tuple[t]=index
            return by_tuple[t].get(canonical(row),())
        for idx in ids:
            epoch,_,rid,ports,reasons=rhs[idx-1]
            tiers={k:[] for k in ('strict','same_physical_union','visible_key_revalidation','cross_address_union')}
            unavailable=any(c not in (0,1) for c in reasons)
            for pos,p in enumerate(ports):
                if p is None:continue
                t,a,v,fields=p;a=tuple(a);row=freeze(fields);norm=canonical(row);last=last_write.get(a,-1)
                sources={k:set() for k in tiers}
                for prior,version,table,values,op in history[a]:
                    if table!=t:continue
                    if values==row and version==v and prior>=last:sources['strict'].add(prior)
                    if prior>=last and canonical(values)==norm:sources['same_physical_union'].add(prior)
                    if canonical(values)==norm:sources['visible_key_revalidation'].add(prior)
                sources['cross_address_union'].update(sources['visible_key_revalidation'])
                # A different physical origin must resolve a live semantic key and recheck mutable/hidden state.
                # Even when a same-address support exists, an earlier recursively closed alternative may help.
                known=depths['cross_address_union']
                if not any(p==0 or p in known for p in sources['cross_address_union']):
                    sources['cross_address_union'].update(pr for pr,old,op in alternatives(t,row))
                for k,parents in sources.items():
                    tiers[k].append(parents)
                    if not parents:missing[k][t]+=1
            for k,sets in tiers.items():
                c=counts[k];known=depths[k]
                some=any(any(pr>0 for pr in possible) for possible in sets)
                all_live=not unavailable and all(sets)
                if mutable is not None:
                    dependencies,unidentified=mutable
                    sets=sets+[set([pr]) for pr in dependencies.get(idx,())]
                closed=not unavailable and (mutable is None or idx not in mutable[1]) and all(any(pr==0 or pr in known for pr in options) for options in sets)
                c['with_prior_rhs']+=some;c['direct_complete_with_initial_or_prior']+=all_live
                if closed:
                    dep=1+max((min(0 if pr==0 else known[pr] for pr in opts if pr==0 or pr in known) for opts in sets),default=0)
                    known[idx]=dep
                if not all_live and k not in examples:examples[k]=dict(run=epoch,rhs=idx,rule=rid,missing_positions=[i for i,x in enumerate(sets) if not x])
        for idx in ids:
            run,rid,ok,outputs=calls[idx-1]
            if not ok:continue
            for op,t,a,version,fields in outputs:
                a=tuple(a);history[a].append((idx,version,t,freeze(fields),op));tables[t].add(a)
        for event in run_events:
            if event[0]=='union':
                high,low=representative(event[1]),representative(event[2])
                if high!=low:uf[high]=low
            elif event[0]=='birth':last_write[0,event[4]]=ids[event[5][0]] if event[5] is not None else float('inf')
            elif event[0]=='write':last_write[1,event[4]]=ids[event[2][0]] if event[2] is not None else float('inf')
        # A later *witnessed* source effect may supersede a prior repair-only write.
        for idx in ids:
            for op,t,a,version,fields in calls[idx-1][3]:
                a=tuple(a)
                if last_write.get(a)==float('inf') and not any(ev[0]=='write' and ev[2] is None and (1,ev[4])==a for ev in run_events):
                    last_write[a]=idx
    return dict(rhs=len(rhs),tiers={k:dict(**c,recursively_closed=len(depths[k]),max_depth=max(depths[k].values(),default=0),
                    top_missing_tables=missing[k].most_common(6)) for k,c in counts.items()},missing_examples=examples)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('data',type=Path);p.add_argument('out',type=Path)
    a=p.parse_args();result={}
    for n in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax'):
        result[n]=measure(a.data/f'v3-{n}');print(n,result[n]['tiers'],flush=True)
        a.out.write_text(json.dumps(result,indent=1)+'\n')

"""Condition the parent-port oracle additionally on the positive old values required at mutable Set sites."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
from merge_ports import additions
from versions import freeze,measure


def requires_old(expr):
    return isinstance(expr,dict) and (expr.get('var')=='old' or any(requires_old(x) for x in expr.get('args',[])))


def obligations(folder,program):
    r=json.loads((folder/'references.json').read_bytes());aud=json.loads((folder/'audit.json').read_bytes())
    source=json.loads(program.read_bytes())['recipe'];names={t['name']:i for i,t in enumerate(source['tables'])}
    tables={i for i,t in enumerate(source['tables']) if t['kind']!='constructor' and requires_old(t.get('merge_expr'))}
    reads=Counter();required=defaultdict(set);missing=defaultdict(list);last={};uf={}
    def canon_id(k):
        while k in uf:
            if uf[k] in uf:uf[k]=uf[uf[k]]
            k=uf[k]
        return k
    def canon(x):
        if isinstance(x,dict):
            if set(x)=={'Eq'}:return {'Eq':canon_id(x['Eq'])}
            return {k:canon(v) for k,v in x.items()}
        if isinstance(x,list):return [canon(v) for v in x]
        return x
    for t,(kind,idx),epoch,row in r['initial']:
        if t in tables and kind==1:last[t,idx]=(0,row[-1])
    by_run=defaultdict(list)
    for i,b in enumerate(r['lhs'],1):by_run[b[0]].append(i)
    sampled=0
    for run,events in enumerate(aud['events'],1):
        ids=by_run[run]
        for e in events:
            if e[0]=='union':
                hi,lo=canon_id(e[1]),canon_id(e[2])
                if hi!=lo:uf[hi]=lo
            if e[0]=='set-input':
                _,source,t,index,keys,old,candidate=e
                if t not in tables or source is None:continue
                sampled+=1;ordinal=ids[source[0]];key=t,index;previous=last.get(key)
                if old is None:reads['source_unique_key_absence_checks']+=1
                elif previous is None:missing[ordinal].append('prior_row_not_identified')
                elif canon(previous[1])!=canon(old):missing[ordinal].append('prior_value_changed_outside_observed_write')
                elif previous[0]<0:missing[ordinal].append('source_less_repair')
                elif previous[0]==ordinal:reads['earlier_effect_of_same_rhs']+=1
                else:
                    reads['old_from_initial' if previous[0]==0 else 'old_from_prior_effective_writer']+=1
                    required[ordinal].add(previous[0])
            if e[0]=='write' and e[3] in tables:
                last[e[3],e[4]]=(ids[e[2][0]] if e[2] is not None else -1,e[7])
    assert sampled>0
    return required,missing,dict(reads)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('data','ref','corpus','out'):p.add_argument(k,type=Path)
    a=p.parse_args();summary={}
    for case in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax'):
        program=a.ref/case/'program.json' if case in ('sum-bits','dot-product') else a.corpus/case/'program.json';folder=a.data/f'mutable-{case}'
        additional,_,_=additions(folder,program)
        before,miss,stats=obligations(folder,program)
        result=measure(folder,additional,mutable=(before,miss))
        summary[case]=dict(stats=stats,unknown=dict(Counter(s for ls in miss.values() for s in ls)),analysis=result)
        print(case,stats,summary[case]['unknown'],result['tiers']['cross_address_union']['recursively_closed'],flush=True)
        a.out.write_text(json.dumps(summary,indent=1)+'\n')

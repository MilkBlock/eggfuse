"""Package compact structural counts and donor-only selection, independently checking typed source plans."""
from argparse import ArgumentParser
from collections import Counter
from pathlib import Path
import json
from hashlib import sha256
from audit import DONORS,HOLDOUT,digest,rule_id


def frequency(cases,kind):
    total=Counter();support=Counter()
    for c in DONORS:
        total.update(cases[c][kind]);support.update(cases[c][kind].keys())
    return total,support


def category(s):
    arity=s[-1];phys=len({tuple(w[1:]) for w in s[3]})
    return 'unary' if arity==1 else 'multi_distinct_refs' if phys>=2 else 'multi_aliased_single_ref'


def contrast(cases):
    transfer={};catalog={}
    for kind in ('pairs','triples'):
        total,support=frequency(cases,kind);allshapes={k:shape for c in DONORS for k,shape in cases[c]['shapes'].items() if k in cases[c][kind]}
        repeated={s for s,n in total.items() if n>=2}
        catalog[kind]={s:dict(shape=allshapes[s],donor_counts=[cases[c][kind].get(s,0) for c in DONORS]) for s in sorted(repeated)}
        t={}
        for name,chosen in [('seen',set(total)),('repeated',repeated),('both_donors',{k for k,n in support.items() if n==2})]:
            t[name]=dict(shapes=len(chosen),donor_occurrences=sum(total[s] for s in chosen),heldout={})
            for c in HOLDOUT:
                a=cases[c];counts=Counter();anch=Counter()
                for s in chosen&a[kind].keys():
                    shape=a['shapes'][s];last=shape if kind=='pairs' else a['shapes'][shape[1]]
                    counts[category(last)]+=a[kind][s]
                    anch[category(last)]+=1
                t[name]['heldout'][c]=dict(children=dict(counts),matched_shapes=dict(anch))
        transfer[kind]=t
    return transfer,catalog


def main():
    p=ArgumentParser();p.add_argument('exp',type=Path);p.add_argument('capture',type=Path);p.add_argument('out',type=Path)
    a=p.parse_args();cases={c:json.loads((a.capture/(c+'.json')).read_bytes()) for c in (*DONORS,*HOLDOUT)}
    out={};checksums={};fingerprints={};helper_rules={}
    for case,raw in cases.items():
        folder=a.exp/('extra-pass3-transfer-v1' if case=='3mm' else 'compact-holdouts-20261121-v1')/(case+'-1703')
        file=folder/'program.json';checksums[case]=sha256(file.read_bytes()).hexdigest()
        rules=json.loads(file.read_bytes())['recipe']['rules'];fps=[rule_id(r) for r in rules]
        fingerprints[case]=fps
        helper_rules[case]=[i for i,r in enumerate(rules) if r['metadata']['name'].startswith('complete-CellSpineView')]
        count=Counter();trip=Counter();init=Counter();helpers=Counter()
        for key,n in raw['pairs'].items():
            producer,child,delta,wires,arity=raw['shapes'][key]
            assert digest([fps[producer],fps[child],delta,wires])==key and delta>=1
            lhs=rules[child]['query'];rhs=rules[producer]['effects'];pins=rules[producer]['query']
            assert [w[0] for w in wires]==[i for i,r in enumerate(lhs) if 'table' in r['call']]
            assert len(wires)==arity and any(w[1]=='op' for w in wires)
            for ci,source,port in wires:
                src=rhs[port] if source=='op' else pins[port]
                assert src['call']['table']==lhs[ci]['call']['table']
            typ=category(raw['shapes'][key]);count[typ]+=n
            if not any('table' in r['call'] for r in pins):init[typ]+=n
            if child in helper_rules[case]:helpers[typ]+=n
        for key,n in raw['triples'].items():
            fst,last,arity=raw['shapes'][key];assert digest([fst,last])==key
            a1=raw['shapes'][fst];a2=raw['shapes'][last];assert a1[1]==a2[0] and arity==a2[-1]
            trip[category(a2)]+=n
        out[case]={k:raw[k] for k in ('counts','parts','census','examples','reference','pair_children_sha','chain_children_sha')}
        for example in out[case]['examples'].values():
            for role in ('producer','child'):
                if role in example:example[role]['source']=example[role]['source'][:180]
        out[case].update(pair_categories=dict(count),triple_terminal_categories=dict(trip),pair_ground_producer=dict(init),pair_view_completion_consumers=dict(helpers),pair_shapes=len(raw['pairs']),triple_shapes=len(raw['triples']))
    transfer,catalog=contrast(cases)
    for kind in ('pairs','triples'):
        for key,entry in catalog[kind].items():
            entry['heldout_counts']={c:cases[c][kind].get(key,0) for c in HOLDOUT}  # attached strictly after donor selection
    case_names=list((*DONORS,*HOLDOUT))
    shapes={}
    for raw in cases.values():
        for key,definition in raw['shapes'].items():
            assert key not in shapes or shapes[key]==definition
            shapes[key]=definition
    index={key:i for i,key in enumerate(sorted(shapes))}
    ledger=[]
    for key in sorted(shapes):
        shape=shapes[key];kind='pairs' if len(shape)==5 else 'triples'
        source_shape=shape if kind=='pairs' else [index[shape[0]],index[shape[1]],shape[2]]
        ledger.append([key,source_shape,[cases[case][kind].get(key,0) for case in case_names]])
    # The archive stores shape and occurrence counts. The full exact trace is regenerated by audit.py.
    (a.out/'shape-counts.json').write_text(json.dumps(dict(order=case_names,shapes=ledger,rule_fingerprints=fingerprints,
          completion_view_rules=helper_rules),separators=(',',':'))+'\n')
    for fname,data in [('results',out),('transfer',transfer),('catalog',catalog),('sources',checksums)]:
        (a.out/(fname+'.json')).write_text(json.dumps(data,indent=1)+'\n')
if __name__=='__main__':main()

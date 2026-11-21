"""Bake authenticated first-hop and connected second-hop certificates against actual released packets."""
import argparse,hashlib,json
from pathlib import Path
from runpy import run_path
HERE=Path(__file__).resolve().parent
joint=run_path(str(HERE.parent/'integral-filter-joint/study.py'))
DONORS=('dot-product','jacobi-1d')
LIMIT=32
def digest(x):
    return hashlib.sha256(json.dumps(x,separators=(',',':'),sort_keys=True).encode()).hexdigest()
def schema_map(program):
    rules=json.loads(program.read_bytes())['recipe']['rules']
    ids=[digest([r['metadata'].get('source_set'),r['metadata'].get('seminaive'),r['query'],r['slots'],r['effects'],r['interface']]) for r in rules]
    index={}
    for i,k in enumerate(ids):index[k]=i if k not in index else None
    return ids,index
def schema_route(path,ids):
    return tuple((ids[p],op,ids[c],slot) for p,op,c,slot in path)
def relink(routes,index):
    out=[]
    for path in routes:
        if all(index.get(p) is not None and index.get(c) is not None for p,op,c,slot in path):
            out.append([[index[p],op,index[c],slot] for p,op,c,slot in path])
    return out
def train(a):
    a.out.mkdir(parents=True,exist_ok=True)
    chosen=[];archive={};gold={}
    for depth in (1,2):
        totals={};local={}
        for case in DONORS:
            program,plan,req=joint['src'].config(a,case);ids,ix=schema_map(program)
            if case not in gold:
                with joint['src'].base.session(a.exp/'compact-vanilla-20261121/vanilla',program) as exact:gold[case]=exact({})
            cfg=joint['settings'](req,'filter_mixed')
            ctrl={'depth':depth}
            if depth==2:ctrl.update(library=relink(chosen,ix),explore_second=True)
            with joint['src'].base.session(a.native,program,plan) as get:v=get(dict(cfg,chain=ctrl))
            assert 'source_error' not in v,v.get('source_error')
            assert v['state_sha']==gold[case]['state_sha'] and v['runs']==gold[case]['runs'] and v['multi']['total_rhs']==gold[case]['rhs_count']
            c=v['integral_root']['chain'];pack=v['integral_packets']['counts']
            assert sum(n for p,n in c['suppressed'])+c['different_owner']==pack['confirmed']
            paths={}
            for p,n in c['suppressed']:
                if len(p)!=depth:continue
                k=schema_route(p,ids)
                if depth==2:assert k[0][2]==k[1][0] and (k[0],) in chosen
                if any(ix.get(i) is None for edge in k for i in (edge[0],edge[2])):continue
                paths[k]=paths.get(k,0)+n;totals[k]=totals.get(k,0)+n
            local[case]=dict(program=hashlib.sha256(program.read_bytes()).hexdigest(),trusted=sum(paths.values()),source_verified=c['commits'],runs=v['runs'],state_sha=v['state_sha'],rhs=v['multi']['total_rhs'],suppressed_by_route=[(k,v)for k,v in sorted(paths.items())],other_owner=c['different_owner'],actual_external=v['root_recipe']['emitted'],raw_available=len(paths))
            print(case,depth,c['commits'],sum(paths.values()),len(paths),flush=True)
        pick=sorted(totals,key=lambda p:(-totals[p],p))[:LIMIT]
        archive[str(depth)]={'selected':pick,'credited':[totals[p] for p in pick],'donors':local,'available':len(totals),'available_credit':sum(totals.values())}
        chosen.extend(pick)
    (a.out/'library.json').write_text(json.dumps(dict(limit=LIMIT,rounds=archive),separators=(',',':'))+'\n')
    print('rounded library',[(k,len(v['selected']),sum(v['credited']))for k,v in archive.items()],flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('exp','native','out'):p.add_argument(n,type=Path)
    train(p.parse_args())

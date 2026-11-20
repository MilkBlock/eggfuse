"""Census and live native execution using two- and three-view codes with two-column forward feasibility."""
import argparse
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
from statistics import median
from time import perf_counter
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('integrated_page',HERE.parent/'integrated-cpu-policy/measure.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)

def config(a,case,views):
    p,plan,_,b=base.setup(a,case);params=base.read(HERE.parent/'single-signature-frontier/admission.json')['parameters']
    q=base.query(b,'all',params)
    q.update(forward=dict(columns=2,budget=4<<20,existence=True,freshness=True,min_candidates=8),atom_constraints=2,
             multi_mode=q['multi_mode'].replace('seallearned',f'seal{views}xlearned'),
             tiered_ports=dict(primary=True,columns=True,evidence_views=views,bytes=1<<20))
    assert q['multi_root_pages'] and q['packed_lookup'] and not q['multi_residual']
    return p,plan,q

def run(a):
    a.out.mkdir(exist_ok=False,parents=True);reports={}
    for case in a.cases:
        for views in a.views:
            p,plan,q=config(a,case,views)
            with ExitStack() as sc:
                vdir=a.exp/'compact-vanilla-20261121'
                gold=sc.enter_context(base.session(vdir/'vanilla-audit',p))({'audit':True})
                invoke=sc.enter_context(base.session(a.binary,p,plan))
                v=invoke(dict(q,prefix_census=True,audit=True));s=base.summarize(v,gold)
                core={k:s[k] for k in ('rhs','neural_rhs','fresh','direct_cells','state_sha','checks','multi','raw','commits','physical','children','root_ids','nested_ids')}
                core['runs']=v['runs'];m=v['multi'];c=m['prefix_census']
                assert c['tuples']==m['paged_tuples']==m['counts']['raw_tuples']>0
                core.update(census=c,ref_bytes=m['ref_bytes'],pages=m['pages'],tier=m['tier'],forward=m['forward'])
                reports[f'{case}/{views}']=core
                (a.out/'results.json').write_text(json.dumps(reports,indent=1)+'\n')
                print(case,views,c['tuples'],[(d['offered'],d['shared'],d['read'],d['shared_read']) for d in c['depth']],flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('binary','exp','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','jacobi-1d','conjugate-gradient'])
    p.add_argument('--views',nargs='+',type=int,default=[2,3])
    run(p.parse_args())

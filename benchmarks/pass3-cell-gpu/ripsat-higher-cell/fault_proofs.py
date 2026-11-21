"""Independently audit all original source and physical ledgers for the actual injected responses."""
from argparse import ArgumentParser
from pathlib import Path
from runpy import run_path
import json
HERE=Path(__file__).resolve().parent;study=run_path(str(HERE/'study.py'));src=study['source']
def run(a):
    a.out.mkdir(parents=True,exist_ok=True);results={}
    for case in a.cases:
        prog,plan,req=src.config(a,case);auth=study['read'](a.authorized/(case+'.json'));rows={}
        with src.base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',prog)as get:gold=get(dict(audit=True))
        for mode in ('direct','let','stale-generation','stale-epoch','duplicate','only-stale','alias-mismatch'):
            cfg=study['settings'](req,auth,mode if mode in ('direct','let') else 'higher',fault=mode if mode not in ('direct','let') else None,audit=True)
            if mode=='let':
                del cfg['strict_named']['set_publication'];cfg['strict_named']['depth']=1
            with src.base.session(a.native,prog,plan)as get:v=get(cfg)
            q,links=study['summary'](v,gold)
            rows[mode]={k:q[k] for k in study['ALIGN']}
            if mode not in ('direct','let'):
                ref='let' if mode in ('only-stale','alias-mismatch') else 'direct'
                for k in study['ALIGN']:
                    assert rows[mode][k]==rows[ref][k],(case,mode,ref,k)
            del v
        results[case]={k:study['previous']['digest'](q)for k,q in rows.items()}
        (a.out/'faults.json').write_text(json.dumps(results,indent=1)+'\n')
        print(case,results[case],flush=True)
if __name__=='__main__':
    p=ArgumentParser(description=__doc__)
    for k in ('exp','native','authorized','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','3mm']);run(p.parse_args())

"""Matched exact and trained execution on source-stable physical Cell stores."""
import argparse,importlib.util,json
from contextlib import ExitStack
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('source_config',HERE.parent/'pair-source-frontier/profile.py')
source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source)
MODES=('hash','arena','page16','page64')

def run(a):
    a.out.mkdir(parents=True,exist_ok=False);report={}
    for case in a.cases:
        p,plan,req=source.config(a,case)
        req.update(header_mode=3,derived_ports={'mode':1,'cache':True},lazy_equations=4)
        vanilla=a.exp/'compact-vanilla-20261121'
        with source.base.session(vanilla/'vanilla-audit',p) as get:
            gold=get({'audit':True})
        rows={'vanilla':dict(ms=[],phases=[],runs=gold['runs'],rhs=gold['rhs_count'])}
        with ExitStack() as stack:
            exact=stack.enter_context(source.base.session(vanilla/'vanilla',p))
            engines={m:stack.enter_context(source.base.session(a.build/m,p,plan)) for m in MODES}
            for m,infer in engines.items():
                v=infer(dict(req,audit=True));q=source.base.summarize(v,gold)
                q.pop('rows');q.pop('work');q.update(ms=[],phases=[],store=v['physical_store'])
                if m!='hash':
                    for k in ('raw','multi','physical','cells','single_winners','multi_winners','root_parents','root_ids','nested_ids','rhs','direct_cells','state_sha'):
                        assert q[k]==rows['hash'][k],(case,m,k)
                    assert q['store']['live']==rows['hash']['store']['live']
                rows[m]=q;del v
                v=infer({'baseline':True,'audit':True})
                checks={k:v[k]==gold[k] for k in ('rhs','writes','resumes','schedule','runs','state_sha')}
                checks['unions']=[[u for u in e if u[0]=='union'] for e in v['events']]==gold['unions']
                assert all(checks.values()),(case,m,checks)
                rows[m+'-exact']=dict(ms=[],phases=[],state_sha=v['state_sha'],checks=checks,store=v['physical_store'])
                del v
            names=list(rows)
            for lap in range(a.repeats+1):
                offset=lap%len(names);seq=names[offset:]+names[:offset]
                for label in seq if lap%2 else reversed(seq):
                    if label=='vanilla':v=exact({})
                    elif label.endswith('-exact'):v=engines[label[:-6]]({'baseline':True})
                    else:v=engines[label](req)
                    assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs']
                    if label not in ('vanilla',) and not label.endswith('-exact'):
                        assert v['multi']['total_rhs']==gold['rhs_count'] and v['root_recipe']['allocated']==rows[label]['root_allocated']
                    if lap:
                        rows[label]['ms'].append(v['ms'])
                        if label!='vanilla':rows[label]['phases'].append(v['phases_ms'])
        for q in rows.values():q['median_ms']=median(q['ms'])
        report[case]=rows;(a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')
        print(case,[(k,round(v['median_ms'],2),v.get('store',{}).get('live')) for k,v in rows.items()],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','build','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','conjugate-gradient','3mm'])
    p.add_argument('--seed',type=int,default=1703);p.add_argument('--repeats',type=int,default=4)
    run(p.parse_args())

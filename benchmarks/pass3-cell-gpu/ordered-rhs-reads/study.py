"""Price exact table-read sharing on the same source engine and the integrated neural path."""
import argparse
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('linked_rhs',HERE.parent/'integrated-cpu-policy/measure.py')
ref=importlib.util.module_from_spec(spec);spec.loader.exec_module(ref)
from study import digest  # compact-recipes helper loaded by linked_rhs

def report_work(work,names):
    index=work.pop('tables')
    work['top_tables']={names[i]:row for i,row in sorted(enumerate(index),key=lambda x:-x[1][1])[:10] if row[0]}
    return work

def run(a):
    a.out.mkdir(parents=True,exist_ok=False);reports={}
    admission=ref.read(HERE.parent/'single-signature-frontier/admission.json')['parameters']
    for case in a.cases:
        p,plan,_,base=ref.setup(a,case)
        names=[t['name'] for t in ref.read(p)['recipe']['tables']]
        with ExitStack() as scope:
            vanilla=scope.enter_context(ref.session(a.exp/'compact-vanilla-20261121/vanilla',p))
            gold=scope.enter_context(ref.session(a.exp/'compact-vanilla-20261121/vanilla-audit',p))({'audit':True})
            native=scope.enter_context(ref.session(a.binary,p,plan))
            arms={'vanilla':dict(ms=[],runs=gold['runs'],rhs=gold['rhs_count'])}
            requests={}
            for network in (False,True):
                prior=None
                variants=((0,'off'),(0,'grouped')) if a.projection else ((0,'off'),(1,'nullary'),(2,'full'))
                for mode,name in variants:
                    if not network and name=='grouped':continue
                    if not network and mode==1:continue
                    arm=('neural-' if network else 'exact-')+name
                    req=ref.query(base,'all',admission) if network else {'baseline':True}
                    req=dict(req,rhs_reads=mode,grouped_root=name=='grouped');requests[arm]=req
                    v=native(dict(req,audit=True,verify_rhs_reads=True))
                    checks={k:v[k]==gold[k] for k in ('rhs','writes','resumes','state_sha','schedule','runs')}
                    checks['unions']=[[e for e in row if e[0]=='union'] for row in v['events']]==gold['unions']
                    assert all(checks.values()),(arm,case,checks)
                    physical=dict(new_cells=v['new_cells'],physical_ids=digest(v['cell_ids']),by_rhs=digest(v['allocations']))
                    if network:
                        q=ref.summarize(v,gold)
                        assert q['neural_rhs']==gold['rhs_count'] and 100*q['direct_cells']>=98*q['fresh']
                        physical.update({k:q[k] for k in ('direct_cells','fresh','single_winners','multi_winners','root_parents','root_ids','nested_ids','raw','wire_hash')})
                    if prior is None:prior=physical
                    else:assert prior==physical,(case,arm)
                    st=report_work(v['rhs_reads'],names)
                    arms[arm]=dict(ms=[],phases=[],checks=checks,state=gold['state_sha'],physical=physical,cache=st)
                    if network and a.projection:
                        result=v['root_recipe']
                        arms[arm]['projection']={k:result[k] for k in ('whole_projections','grouped_header_checks','whole_commits','root_header_checks','sealed','applied','allocated')}
                        if name=='grouped':
                            assert result['whole_projections'] and result['whole_commits']
                            broken=native(dict(req,root_projection_fault=True))
                            assert 'root recipe changed across source commit' in broken['source_error']
                            arms[arm]['rejected_missing_slot']=[broken['runs'],broken['source_error']]
                    del v
            order=list(arms)
            for trial in range(a.repeats+1):
                i=trial%len(order);ordered=order[i:]+order[:i]
                for arm in reversed(ordered) if trial%2 else ordered:
                    v=vanilla({}) if arm=='vanilla' else native(requests[arm])
                    assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs']
                    if arm!='vanilla':
                        stats=v['rhs_reads'];prev=arms[arm]['cache']
                        assert stats['cells']==prev['cells'] and stats['constructor_requests']==prev['constructor_requests']
                        assert stats['eligible_hits_keymiss_stampmiss']==prev['eligible_hits_keymiss_stampmiss']
                        if trial:arms[arm]['phases'].append(v['phases_ms'])
                    if trial:arms[arm]['ms'].append(v['ms'])
            for v in arms.values():
                v['median_ms']=median(v['ms'])
                if 'phases' in v:v['median_phase_ms']=list(map(median,zip(*v['phases'])))
            reports[case]=arms;(a.out/'results.json').write_text(json.dumps(reports,indent=1)+'\n')
            print(case,[(n,round(v['median_ms'],2),v.get('cache',{}).get('eligible_hits_keymiss_stampmiss',[0,0])[1]) for n,v in arms.items()],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for f in ('binary','exp','out'):p.add_argument(f,type=Path)
    p.add_argument('--projection',action='store_true')
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','jacobi-1d','conjugate-gradient'])
    p.add_argument('--repeats',type=int,default=6)
    run(p.parse_args())

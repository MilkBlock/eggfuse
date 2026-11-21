"""Compare the complete singleton source/physical ledgers with and without exact scalar certificates."""
import argparse
from contextlib import ExitStack
import hashlib
import importlib.util
import json
from pathlib import Path
from statistics import median
from time import perf_counter

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('profile_loader',HERE.parent/'pair-source-frontier/profile.py')
profile=importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)
ALIGN=('single_winners','multi_winners','root_parents','root_ids','nested_ids','cells','rhs','direct_cells','children','multi','state_sha','full_single','decisions')
def digest(x):
    return hashlib.sha256(json.dumps(x,separators=(',',':'),sort_keys=True).encode()).hexdigest()

def check(case,q,base):
    assert q['aligned'] and all(q['checks'].values()),case
    for k in ALIGN:
        assert q[k]==base[k],(case,k,q[k],base[k])
    assert q['eligible'] and q['omitted']>0 and q['omitted']==q['audited']
    assert q['emitted']+q['omitted']==base['emitted']
    assert q['verified']+q['omitted']==base['verified']
    assert q['complete_scores']==base['complete_scores']

def run(a):
    a.out.mkdir(parents=True,exist_ok=True)
    report={}
    for case in a.cases:
        prog,plans,cfg=profile.config(a,case)
        cfg.update(header_mode=3,derived_ports=dict(mode=1,cache=True),lazy_equations=4,
                   multi_page_tuples=8192,proposal_wave=65536)
        modes={k:dict(cfg,rows=dict(cfg['rows'],scalar_certificates=k=='on')) for k in ('off','on')}
        reference=a.exp/'compact-vanilla-20261121'
        with profile.base.session(reference/'vanilla-audit',prog) as vanilla: gold=vanilla(dict(audit=True))
        rows={'vanilla':dict(ms=[],wall_ms=[],runs=gold['runs'],rhs=gold['rhs_count'])}
        with ExitStack() as stack:
            exact=stack.enter_context(profile.base.session(reference/'vanilla',prog))
            for k,req in modes.items():
                with profile.base.session(a.native,prog,plans) as separate:
                    v=separate(dict(req,audit=True))
                assert 'source_error' not in v,v.get('source_error')
                q=profile.base.summarize(v,gold);del q['rows'],q['work']
                s=v['single'];ad=s['adaptive_rows'];counts={i:x for i,x in enumerate(ad['scalar_certificates']) if x['examined']}
                q.update(verified=s['work'][2],complete_scores=s['work'][:2],emitted=ad['stats']['emitted'],
                         decisions=ad['decision_digest'],full_single=digest(s['committed']),eligible=len(counts),
                         omitted=sum(x['stale']+x['missing'] for x in counts.values()),
                         audited=sum(x['audited'] for x in counts.values()),
                         module=counts,single_rules=s['rules'],ms=[],wall_ms=[],phases=[])
                if k=='on':check(case,q,rows['off'])
                rows[k]=q
                print(case,k,q['verified'],q['omitted'],flush=True)
                del v
            infer=stack.enter_context(profile.base.session(a.native,prog,plans))
            labels=list(rows)
            for i in range(1+a.repeats):
                seq=labels[i%3:]+labels[:i%3]
                for k in seq if i%2 else reversed(seq):
                    start=perf_counter();v=exact({}) if k=='vanilla' else infer(dict(modes[k],audit=False));wall=(perf_counter()-start)*1000
                    assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs']
                    if k!='vanilla':assert v['multi']['total_rhs']==gold['rhs_count'] and v['root_recipe']['allocated']==rows[k]['root_allocated']
                    if i:
                        rows[k]['ms'].append(v['ms']);rows[k]['wall_ms'].append(wall)
                        if k!='vanilla':rows[k]['phases'].append(v['phases_ms'])
            for q in rows.values():q['median_ms']=median(q['ms']);q['median_wall_ms']=median(q['wall_ms'])
        report[case]=rows
        (a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')
        print(case,[(k,q['median_ms']) for k,q in rows.items()],flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['conjugate-gradient','3mm'])
    p.add_argument('--repeats',type=int,default=6)
    run(p.parse_args())

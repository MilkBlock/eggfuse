"""Evaluate retained scalar epochs against exact per-lane checks on the complete native runtime."""
import argparse
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
from statistics import median
from time import perf_counter

HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('negative_source',HERE.parent/'single-pivot-certificates/study.py')
negative=importlib.util.module_from_spec(sp);sp.loader.exec_module(negative)
profile=negative.profile

def check(case,rows):
    base,old,new=[rows[k] for k in ('off','filter','delta')]
    for candidate in (old,new):negative.check(case,candidate,base)
    for key in (*negative.ALIGN,'physical','commits','emitted','wire_hash','wire_bytes','raw','verified','audited'):
        assert new[key]==old[key],(case,key)
    for i,row in old['module'].items():
        for k in ('missing','stale','audited'):assert row[k]==new['module'][i][k],(case,i,k)
    work=new['delta']
    assert work['audited_pivot_hits']==work['pivot_hits']>0
    assert work['audited_ports']==work['point_uses']>0 and work['examined']>0
    assert work['point_uses']==work['point_lookups']+work['same_version_hits']+work['changed_generation_refreshes']
    assert work['cross_run_reuses'] and work['scalar_fresh_old_pivot'] and work['union_resets']>0
    assert work['stale']+work['missing']==new['audited'] and work['peak_entries']<=131072

def run(a):
    a.out.mkdir(parents=True,exist_ok=True);results={}
    for case in a.cases:
        prog,plan,req=profile.config(a,case)
        req.update(header_mode=3,derived_ports=dict(mode=1,cache=True),lazy_equations=4,multi_page_tuples=8192,proposal_wave=65536)
        modes={k:dict(req,rows=dict(req['rows'],scalar_certificates=k!='off',scalar_delta_frontier=k=='delta')) for k in ('off','filter','delta')}
        vd=a.exp/'compact-vanilla-20261121'
        with profile.base.session(vd/'vanilla-audit',prog) as get:gold=get(dict(audit=True))
        rows={'vanilla':dict(ms=[],wall_ms=[],runs=gold['runs'],rhs=gold['rhs_count'])}
        for name,cfg in modes.items():
            with profile.base.session(a.native,prog,plan) as infer:v=infer(dict(cfg,audit=True))
            assert 'source_error' not in v,v.get('source_error')
            q=profile.base.summarize(v,gold);del q['rows'],q['work']
            s=v['single'];ad=s['adaptive_rows'];counts={i:x for i,x in enumerate(ad['scalar_certificates']) if x['examined']}
            q.update(verified=s['work'][2],complete_scores=s['work'][:2],emitted=ad['stats']['emitted'],delta=ad['delta'],layout=ad['delta_layout'],
                     decisions=ad['decision_digest'],full_single=negative.digest(s['committed']),eligible=len(counts),
                     omitted=sum(x['stale']+x['missing'] for x in counts.values()),audited=sum(x['audited'] for x in counts.values()),
                     module=counts,ms=[],wall_ms=[],phases=[])
            rows[name]=q
            del v
            print(case,name,q['omitted'],q['delta']['point_lookups'],flush=True)
        check(case,rows)
        with ExitStack() as ctx:
            infer=ctx.enter_context(profile.base.session(a.native,prog,plan));vanilla=ctx.enter_context(profile.base.session(vd/'vanilla',prog))
            names=list(rows)
            for lap in range(1+a.repeats):
                order=names[lap%len(names):]+names[:lap%len(names)]
                for k in order if lap%2 else reversed(order):
                    start=perf_counter();v=vanilla({}) if k=='vanilla' else infer(dict(modes[k],audit=False));wall=(perf_counter()-start)*1000
                    assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs']
                    if k!='vanilla':assert v['root_recipe']['allocated']==rows[k]['root_allocated'] and v['multi']['total_rhs']==gold['rhs_count']
                    if k=='delta':
                        w=v['single']['adaptive_rows']['delta']
                        assert w['audited_ports']==w['mask_ns']==w['publication_ns']==0 and w['point_lookups']==rows[k]['delta']['point_lookups']
                    if lap:
                        rows[k]['ms'].append(v['ms']);rows[k]['wall_ms'].append(wall)
                        if k!='vanilla':rows[k]['phases'].append(v['phases_ms'])
            cfg=modes['delta'];clocks=[]
            for _ in range(3):
                v=infer(dict(cfg,rows=dict(cfg['rows'],scalar_frontier_profile=True)))
                w=v['single']['adaptive_rows']['delta'];assert v['state_sha']==gold['state_sha'] and w['mask_ns'] and w['publication_ns']
                clocks.append([w['mask_ns']/1e6,w['publication_ns']/1e6])
            rows['delta']['diagnostic_ms']=clocks
        for q in rows.values():q['median_ms']=median(q['ms']);q['median_wall_ms']=median(q['wall_ms'])
        results[case]=rows;(a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
        print(case,[(k,round(v['median_ms'],2))for k,v in rows.items()],flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['conjugate-gradient','3mm']);p.add_argument('--repeats',type=int,default=6)
    run(p.parse_args())

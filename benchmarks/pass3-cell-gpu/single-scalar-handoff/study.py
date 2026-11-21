"""Hand the exact scalar-function identity and version from issue to native verification."""
import argparse
import importlib.util
from contextlib import ExitStack
import json
from pathlib import Path
from statistics import median
from time import perf_counter

HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('negative_proofs',HERE.parent/'single-pivot-certificates/study.py')
negative=importlib.util.module_from_spec(sp)
sp.loader.exec_module(negative)
profile=negative.profile

def check(case,rows):
    base=rows['off'];negative.check(case,rows['filter'],base);p=rows['ports']
    negative.check(case,p,base)
    for key in (*negative.ALIGN,'physical','raw','emitted','commits','wire_hash','wire_bytes','omitted','verified'):
        assert p[key]==rows['filter'][key],(case,key)
    assert p['point_transfers'][0]==p['point_transfers'][1]>0
    assert 0<p['point_transfers'][0]<=sum(c['sealed_points'] for c in p['module'].values())
    for k in ('off','filter'):assert rows[k]['point_transfers']==[0,0]
    assert rows['fault']['explicit_rejection'] and rows['fault']['runs']<rows['vanilla']['runs']

def run(a):
    a.out.mkdir(parents=True,exist_ok=True)
    results={}
    for case in a.cases:
        prog,plan,req=profile.config(a,case)
        req.update(header_mode=3,derived_ports=dict(mode=1,cache=True),lazy_equations=4,multi_page_tuples=8192,proposal_wave=65536)
        modes={mode:dict(req,rows=dict(req['rows'],scalar_certificates=mode!='off',scalar_handoff=mode=='ports')) for mode in ('off','filter','ports')}
        vd=a.exp/'compact-vanilla-20261121'
        with profile.base.session(vd/'vanilla-audit',prog) as get:gold=get(dict(audit=True))
        rows={'vanilla':dict(rhs=gold['rhs_count'],runs=gold['runs'],ms=[],wall_ms=[])}
        for name,cfg in modes.items():
            with profile.base.session(a.native,prog,plan) as infer:v=infer(dict(cfg,audit=True))
            assert 'source_error' not in v,v.get('source_error')
            q=profile.base.summarize(v,gold);del q['rows'],q['work']
            s=v['single'];ad=s['adaptive_rows'];counts={i:x for i,x in enumerate(ad['scalar_certificates']) if x['examined']}
            q.update(module=counts,eligible=len(counts),audited=sum(x['audited'] for x in counts.values()),
                     omitted=sum(x['missing']+x['stale'] for x in counts.values()),verified=s['work'][2],
                     complete_scores=s['work'][:2],emitted=ad['stats']['emitted'],full_single=negative.digest(s['committed']),
                     decisions=ad['decision_digest'],point_transfers=ad['point_transfers'],
                     logical_table_reads=s['work'][3],ms=[],wall_ms=[],phases=[])
            rows[name]=q
            print(case,name,ad['point_transfers'],flush=True)
            del v
        cfg=modes['ports']
        with profile.base.session(a.native,prog,plan) as infer:fault=infer(dict(cfg,rows=dict(cfg['rows'],fault_scalar_epoch=True)))
        rows['fault']=dict(explicit_rejection='invalid scalar point witness' in fault.get('source_error',''),runs=fault['runs'],source_error=fault.get('source_error'))
        check(case,rows)
        with ExitStack() as stack:
            infer=stack.enter_context(profile.base.session(a.native,prog,plan));native=stack.enter_context(profile.base.session(vd/'vanilla',prog))
            names=['vanilla',*modes]
            for lap in range(1+a.repeats):
                seq=names[lap%4:]+names[:lap%4]
                for n in seq if lap%2 else reversed(seq):
                    start=perf_counter();v=native({}) if n=='vanilla' else infer(dict(modes[n],audit=False));wall=1000*(perf_counter()-start)
                    assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs']
                    if n!='vanilla':
                        assert v['root_recipe']['allocated']==rows[n]['root_allocated'] and v['multi']['total_rhs']==gold['rhs_count']
                        assert v['single']['adaptive_rows']['point_transfers']==[rows[n]['point_transfers'][0],0]
                    if lap:
                        rows[n]['ms'].append(v['ms']);rows[n]['wall_ms'].append(wall)
                        if n!='vanilla':rows[n]['phases'].append(v['phases_ms'])
        for n in names:
            rows[n]['median_ms']=median(rows[n]['ms']);rows[n]['median_wall_ms']=median(rows[n]['wall_ms'])
        results[case]=rows
        (a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
        print(case,[(k,round(rows[k]['median_ms'],2)) for k in names],flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('exp','native','out'):p.add_argument(key,type=Path)
    p.add_argument('--cases',nargs='+',default=['conjugate-gradient','3mm'])
    p.add_argument('--repeats',type=int,default=6)
    run(p.parse_args())

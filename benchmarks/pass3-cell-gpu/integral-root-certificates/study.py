"""Measure native independently released one-hop certificates and original token traffic."""
import argparse
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
from statistics import median
from time import perf_counter

HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('integral_profile',HERE.parent/'pair-source-frontier/profile.py')
src=importlib.util.module_from_spec(sp);sp.loader.exec_module(src)
LEDGERS=('checks','single_winners','multi_winners','root_ids','root_parents','nested_ids','cells','rhs',
         'direct_cells','raw','physical','commits','wire_hash','wire_bytes','multi','children','state_sha','applied')

def check(case,rows):
    off=rows['off']; v=rows['verify']; a=rows['apply']
    for q in (v,a):
        assert q['aligned'] and all(q['checks'].values())
        assert all(q[k]==off[k] for k in LEDGERS),(case,'source')
        info=q['integral'];c=info['counts'];hist=info['fanout']
        if 'complete_receipts' in c:assert c['credited']==c['complete_receipts']+c['reconstructed_receipts']
        assert c['baseline_commits']==off['rhs'] and c['resumed']==rows['vanilla']['spine']
        assert c['external_seeds']==sum(hist.values())
        assert c['credited']==sum(int(k)*n for k,n in hist.items())>0
        assert c['credited']+c['no_proposal']+c['wrong_owner']+c['wrong_witness']+c.get('wrong_anchor',0)+c['deep_resumes']==c['resumed']
        assert c['credited']+c['duplicate_or_unconsumed']+info['uncounted_last_run_offers']==c['offers']
        assert all(l+r<=total for l,r,total in zip(c['root_outputs'],c['child_outputs'],c['total_outputs']))
    va=v['integral']['counts']; aa=a['integral']['counts']
    for k in va:
        if k!='swapped':assert va[k]==aa[k],(case,k)
    assert va['swapped']==0 and aa['swapped']==aa['credited']
    assert v['integral']['routes']==a['integral']['routes'] and v['integral']['fanout']==a['integral']['fanout']
    assert rows['wrong_owner']['rejected']

def run(a):
    a.out.mkdir(parents=True,exist_ok=True);results={}
    for case in a.cases:
        program,plans,req=src.config(a,case)
        req.update(header_mode=3,derived_ports=dict(mode=1,cache=True),lazy_equations=4,multi_page_tuples=8192,proposal_wave=65536)
        vd=a.exp/'compact-vanilla-20261121'
        with src.base.session(vd/'vanilla-audit',program) as get:gold=get(dict(audit=True))
        rows={'vanilla':dict(ms=[],wall_ms=[],runs=gold['runs'],rhs=gold['rhs_count'],spine=sum(x[0] for x in gold['resumes']))}
        modes=('off','verify','apply')
        for mode in modes:
            with src.base.session(a.native,program,plans) as infer:v=infer(dict(req,integral_root=mode,audit=True))
            assert 'source_error' not in v,v.get('source_error')
            q=src.base.summarize(v,gold);del q['rows'],q['work']
            q.update(integral=v['integral_root'],issued_merge_records=len(v['merge_child']['issued']),ms=[],wall_ms=[])
            rows[mode]=q
            print(case,mode,q['integral']['counts'] if mode!='off' else q['rhs'],flush=True)
            del v
        with src.base.session(a.native,program,plans) as infer:fault=infer(dict(req,integral_root='wrong-owner'))
        rows['wrong_owner']=dict(rejected='integral certificate owner, Run or binding mismatch' in fault.get('source_error',''),
                                 completed_runs=fault['runs'],source_error=fault.get('source_error'))
        check(case,rows)
        with ExitStack() as stack:
            infer=stack.enter_context(src.base.session(a.native,program,plans));exact=stack.enter_context(src.base.session(vd/'vanilla',program))
            names=['vanilla',*modes]
            for lap in range(1+a.repeats):
                seq=names[lap%4:]+names[:lap%4]
                for mode in seq if lap%2 else reversed(seq):
                    start=perf_counter();v=exact({}) if mode=='vanilla' else infer(dict(req,integral_root=mode,audit=False));wall=(perf_counter()-start)*1000
                    assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs']
                    if mode!='vanilla':assert v['root_recipe']['allocated']==rows[mode]['root_allocated'] and v['multi']['total_rhs']==gold['rhs_count']
                    if mode in ('verify','apply'):assert v['integral_root']==rows[mode]['integral']
                    if lap:rows[mode]['ms'].append(v['ms']);rows[mode]['wall_ms'].append(wall)
        for n in names:rows[n]['median_ms']=median(rows[n]['ms']);rows[n]['median_wall_ms']=median(rows[n]['wall_ms'])
        results[case]=rows;(a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
        print(case,[(k,round(rows[k]['median_ms'],2))for k in names],flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','3mm']);p.add_argument('--repeats',type=int,default=4)
    run(p.parse_args())

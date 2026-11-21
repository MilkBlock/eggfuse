"""Audit physical Cell placement and time the complete engine with matched forecasts."""
import argparse
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
from statistics import median
from time import perf_counter

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('source_profile', HERE.parent/'pair-source-frontier/profile.py')
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)
IDENTITY = ('raw','multi','physical','cells','single_winners','multi_winners','root_parents','root_ids',
            'nested_ids','rhs','direct_cells','state_sha','commits','children','wire_hash','score_digest')
FORECAST = ('used','granted','fresh','fallback','requested','redeemed','authorized_lanes','preconstructed')
PLACEMENT = ('early_heap_preserved','early_heap_relocated','selected_unallocated','inline_address_moved',
             'inline_address_preserved','inline_spilled_at_publication')

def configurations(req):
    base = dict(req,header_mode=3,derived_ports=dict(mode=1,cache=True),lazy_equations=4,
                multi_page_tuples=8192,proposal_wave=65536)
    policy = json.loads((HERE.parent/'speculative-allocation-policy/policy.json').read_text())
    spec = dict(timing='run',policy='score',storage='group',cap=8192,
                weights=policy['models']['run']['coverage']['weights'])
    configs = {f'off-{k}':(k,base) for k in ('vec','inline1','inline2')}
    for place in ('move','resident'):
        for layout, executable, defer in [('vec','vec',False),('lazy','vec',True),('inline1','inline1',True),('inline2','inline2',True)]:
            configs[f'{place}-{layout}'] = executable,dict(base,spec_cells=dict(
                spec,resident_headers=place=='resident',page_width=64,defer_facts=defer))
    return configs

def check(case,name,q,rows):
    assert all(q['checks'].values()) and q['aligned']
    if name != 'off-vec':
        assert all(q[k]==rows['off-vec'][k] for k in IDENTITY),(case,name,'source/physical')
        for k in ('facts','cells','empty'):
            assert q['layout'][k]==rows['off-vec']['layout'][k],(name,k)
    if name.startswith('off-'):
        return
    c = q['staging']
    assert c['granted']==c['preconstructed']==sum(c[k] for k in ('heap_at_birth','inline_at_birth','unallocated_at_birth'))
    assert c['used']==c['direct_fresh']+c['promoted']==sum(c[k] for k in PLACEMENT)
    assert c['payload_identity']==c['early_heap_preserved']+c['inline_address_preserved']
    if name.endswith('-lazy'):
        assert c['selected_unallocated']==c['used']
    elif '-inline' in name:
        prefix = 'inline_address_preserved' if name.startswith('resident') else 'inline_address_moved'
        assert c[prefix]>0 and c[prefix]+c['inline_spilled_at_publication']==c['used']
        assert c['inline_at_birth']==c['granted']
    else:
        assert c['early_heap_preserved']==c['used'] and c['heap_at_birth']==c['granted']
    if name.startswith('resident'):
        r=q['resident']
        assert r['same_address']==r['published']==c['used'] and r['old_run_reads']>0
    if name!='move-vec':
        assert all(c[k]==rows['move-vec']['staging'][k] for k in FORECAST),(case,name,'staging')

def run(a):
    a.out.mkdir(parents=True,exist_ok=True)
    result={}
    vd=a.exp/'compact-vanilla-20261121'
    for case in a.cases:
        program,plans,req=source.config(a,case)
        configs=configurations(req)
        with source.base.session(vd/'vanilla-audit',program) as ref:
            gold=ref(dict(audit=True))
        rows={'vanilla':dict(ms=[],wall_ms=[],runs=gold['runs'],rhs=gold['rhs_count'])}
        for name,(exe,cfg) in configs.items():
            with source.base.session(a.build/exe,program,plans) as infer:
                v=infer(dict(cfg,audit=True))
            assert 'source_error' not in v,v.get('source_error')
            q=source.base.summarize(v,gold)
            del q['rows'],q['work']
            q.update(layout=v['fact_lanes'],score_digest=v['single']['adaptive_rows']['decision_digest'],
                     resident=v['resident_slabs'],ms=[],wall_ms=[],phase_ms=[])
            if not name.startswith('off-'):
                q['staging']=v['spec_cells']['counts']
            check(case,name,q,rows)
            rows[name]=q
            print(case,name,'audit',q['layout'],flush=True)
            del v
        with ExitStack() as stack:
            native=stack.enter_context(source.base.session(vd/'vanilla',program))
            engines={exe:stack.enter_context(source.base.session(a.build/exe,program,plans))
                     for exe in ('vec','inline1','inline2')}
            names=list(rows)
            for lap in range(1+a.repeats):
                offset=lap%len(names); seq=names[offset:]+names[:offset]
                for name in seq if lap%2 else reversed(seq):
                    start=perf_counter()
                    if name=='vanilla':v=native({})
                    else:
                        exe,cfg=configs[name];v=engines[exe](dict(cfg,audit=False))
                    wall_ms=1000*(perf_counter()-start)
                    assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs']
                    if name!='vanilla':
                        assert v['multi']['total_rhs']==gold['rhs_count']
                        assert v['root_recipe']['allocated']==rows[name]['root_allocated']
                    if lap:
                        rows[name]['ms'].append(v['ms']);rows[name]['wall_ms'].append(wall_ms)
                        if name!='vanilla':rows[name]['phase_ms'].append(v['phases_ms'])
                print(case,'lap',lap,flush=True)
        for q in rows.values():
            q['median_ms']=median(q['ms']);q['median_wall_ms']=median(q['wall_ms'])
        result[case]=rows
        (a.out/'results.json').write_text(json.dumps(result,indent=1)+'\n')
        print(case,[(k,round(v['median_ms'],2)) for k,v in rows.items()],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','build','out'):p.add_argument(k,type=Path)
    p.add_argument('--seed',type=int,default=1703)
    p.add_argument('--repeats',type=int,default=4)
    p.add_argument('--cases',nargs='+',default=['conjugate-gradient','3mm'])
    run(p.parse_args())

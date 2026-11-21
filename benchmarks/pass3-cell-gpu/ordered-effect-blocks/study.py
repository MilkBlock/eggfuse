"""Measure actual ordered block execution, including the cost of compiling touched groups."""
import argparse
import importlib.util
import json
from contextlib import ExitStack
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('source_pair',HERE.parent/'pair-source-frontier/study.py')
common=importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)
PHASES=('search','rhs','repair','publish','deliver')


def run(a):
    a.out.mkdir(parents=True,exist_ok=False)
    by_source={}
    for case in a.cases:
        program,plans,req=common.common.config(a,case)
        req.update(header_mode=3,derived_ports={'mode':1,'cache':True},lazy_equations=4)
        cases={'off':req,'positions':dict(req,ordered_effect_blocks=1),'wires':dict(req,ordered_effect_blocks=2)}
        if a.writers:
            cases={'off':req,'wires':cases['wires'],'write':dict(req,ordered_effect_blocks=3),
                   'both':dict(req,ordered_effect_blocks=4),'reuse-key':dict(req,ordered_effect_blocks=5),'absorbed':dict(req,ordered_effect_blocks=6)}
        ref_dir=a.exp/'compact-vanilla-20261121'
        with common.base.session(ref_dir/'vanilla-audit',program) as source:
            gold=source(dict(audit=True))
        with ExitStack() as stack:
            infer=stack.enter_context(common.base.session(a.native,program,plans))
            exact=stack.enter_context(common.base.session(ref_dir/'vanilla',program))
            results={'vanilla':dict(runs=gold['runs'],rhs=gold['rhs_count'],ms=[])}
            for name,cfg in cases.items():
                value=infer(dict(cfg,audit=True))
                assert 'source_error' not in value,(case,name,value.get('source_error'))
                row=common.base.summarize(value,gold)
                row.pop('rows');row.pop('work')
                row.update(counts=value['multi']['counts'],block=value['ordered_effect_blocks'],samples=[])
                results[name]=row
                if name!='off':
                    for field in ('single_winners','multi_winners','cells','state_sha','root_parents','root_ids','nested_ids',
                                  'rhs','direct_cells','raw','multi','commits','physical','children'):
                        assert row[field]==results['off'][field],(case,name,field)
                    if name!='write':
                        assert row['block']['dispatched'] and row['block']['multirow_bindings'] and row['block']['skipped_copies']
                    else:assert row['block']['dispatched']==0
                if name in ('write','both','reuse-key','absorbed'):
                    w=row['block']['writer']
                    assert w['calls']==w['audited']==w['changed']+w['unchanged'] and w['calls']>0
                    assert w['calls']==w['full_key_probes']+w['reused_key']
                if name=='wires':assert row['block']['rewired_occurrences']==row['block']['audited_fields']>0
            if case==a.cases[0] and not a.writers:
                failure=infer(dict(cases['wires'],audit=True,ordered_effect_fault=True))
                assert failure.get('source_error')=='ordered effect wire disagrees with source operand',failure.get('source_error')
                results['wires']['wrong_operand_rejected']=True
            names=list(results)
            for i in range(a.repeats+1):
                order=names[i%len(names):]+names[:i%len(names)]
                for name in order if i%2 else reversed(order):
                    v=exact({}) if name=='vanilla' else infer(dict(cases[name],audit=False))
                    assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs']
                    if name!='vanilla':
                        assert v['root_recipe']['allocated']==results[name]['root_allocated']
                        assert v['ordered_effect_blocks']['audited_fields']==0
                        for f in ('plans','dispatched','skipped_copies','rewired_occurrences','group_rows'):
                            assert v['ordered_effect_blocks'][f]==results[name]['block'][f],(case,name,f)
                        if i:
                            phases=dict(zip(PHASES,v['phases_ms']))
                            if 'lower_ns' in v['ordered_effect_blocks']:
                                phases['lowering']=v['ordered_effect_blocks']['lower_ns']/1e6
                            results[name]['samples'].append(phases)
                    if i:results[name]['ms'].append(v['ms'])
            for row in results.values():row['median_ms']=median(row['ms'])
        by_source[case]=results
        (a.out/'results.json').write_text(json.dumps(by_source,indent=1)+'\n')
        print(case,[(name,round(v['median_ms'],2),round(median(x['rhs'] for x in v['samples']),2) if 'samples' in v else None) for name,v in results.items()],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','conjugate-gradient','3mm'])
    p.add_argument('--writers',action='store_true')
    p.add_argument('--seed',type=int,default=1703);p.add_argument('--repeats',type=int,default=4)
    run(p.parse_args())

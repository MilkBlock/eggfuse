"""Factor the verification and ordered effects both online and under a separately labeled oracle."""
import argparse,importlib.util,json
from contextlib import ExitStack
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('whole_source',HERE.parent/'pair-source-frontier/profile.py')
source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source)
PHASES=('search','rhs','repair','publication','delivery')


def run(a):
    a.out.mkdir(parents=True,exist_ok=False)
    results={}
    for case in a.cases:
        program,plans,req=source.config(a,case)
        core=dict(req,header_mode=3,derived_ports={'mode':1,'cache':True},lazy_equations=4,multi_page_tuples=8192,factor_page=0)
        pages=dict(factor_page=2,page_premises=9,coordinate_verify=2)
        effects=dict(ordered_effect_blocks=4)
        repair=dict(ordered_repair=7)
        cfg={}
        for oracle in ('live','positive'):
            for key,extra in [('original',{}),('pages',pages),('effects',effects),('repair',repair),('joint',dict(pages,**effects,**repair))]:
                if not a.transfer_only or key in ('original','joint'):
                    cfg[oracle+'-'+key]=dict(core,**extra,receipt_oracle=oracle)
        vdir=a.exp/'compact-vanilla-20261121'
        with source.base.session(vdir/'vanilla-audit',program) as original:gold=original({'audit':True})
        rows={'vanilla':dict(ms=[],rhs=gold['rhs_count'],runs=gold['runs'])}
        with ExitStack() as stack:
            exact=stack.enter_context(source.base.session(vdir/'vanilla',program))
            infer=stack.enter_context(source.base.session(a.native,program,plans))
            capture=infer(dict(core,receipt_oracle='capture'))
            assert capture['state_sha']==gold['state_sha'] and capture['multi']['total_rhs']==gold['rhs_count']
            for arm,request in cfg.items():
                out=infer(dict(request,audit=True))
                assert 'source_error' not in out,(case,arm,out.get('source_error'))
                q=source.base.summarize(out,gold);q.pop('rows');q.pop('work')
                q['verified_roots']=q.pop('neural_rhs');q['online_root_rhs']=out['online_neural_rhs']
                family,action=arm.split('-')
                assert q['online_root_rhs']==(gold['rhs_count'] if family=='live' else 0)
                q.update(repair_work=out.get('ordered_repair'),words=out['multi']['word_verifier'],block=out['multi']['blocks'],effects=out['ordered_effect_blocks'],phase_ms=[])
                if action in ('joint','pages'):
                    assert q['words']['audited']>0 and q['block']['completed']>0
                if arm!='live-original':
                    for f in ('single_winners','multi_winners','cells','state_sha','root_parents','root_ids','nested_ids','rhs','direct_cells'):
                        assert q[f]==rows['live-original'][f],(case,arm,f)
                if action!='original':
                    for f in ('raw','multi','commits','physical','children'):
                        assert q[f]==rows[family+'-original'][f],(case,arm,f)
                rows[arm]=q;del out
            names=list(rows)
            for lap in range(1+a.repeats):
                shift=lap%len(names);order=names[shift:]+names[:shift]
                for arm in order if lap%2 else reversed(order):
                    out=exact({}) if arm=='vanilla' else infer(cfg[arm])
                    assert out['state_sha']==gold['state_sha'] and out['runs']==gold['runs']
                    if arm!='vanilla':
                        assert out['online_neural_rhs']==rows[arm]['online_root_rhs']
                        assert out['root_recipe']['allocated']==rows[arm]['root_allocated']
                    if lap:
                        rows[arm]['ms'].append(out['ms'])
                        if arm!='vanilla':rows[arm]['phase_ms'].append(dict(zip(PHASES,out['phases_ms'])))
        for row in rows.values():row['median_ms']=median(row['ms'])
        results[case]=rows;(a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
        print(case,[(k,round(v['median_ms'],2)) for k,v in rows.items()],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','conjugate-gradient','3mm'])
    p.add_argument('--transfer-only',action='store_true')
    p.add_argument('--seed',type=int,default=1703);p.add_argument('--repeats',type=int,default=4)
    run(p.parse_args())

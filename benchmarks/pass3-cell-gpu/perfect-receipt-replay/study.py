"""Measure oracle ceilings; trace-supplied parents receive zero online discovery credit."""
import argparse,importlib.util,json
from contextlib import ExitStack
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('source_frames',HERE.parent/'pair-source-frontier/profile.py')
config=importlib.util.module_from_spec(spec);spec.loader.exec_module(config)
base=config.base
ARMS=['live','all','single','multi','positive']


def measure(a):
    a.out.mkdir(parents=True,exist_ok=False)
    results={}
    for case in a.cases:
        p,plan,req=config.config(a,case)
        req.update(header_mode=3,derived_ports={'mode':1,'cache':True},lazy_equations=4,multi_page_tuples=8192)
        vdir=a.exp/'compact-vanilla-20261121'
        with base.session(vdir/'vanilla-audit',p) as v:gold=v({'audit':True})
        with ExitStack() as stack:
            infer=stack.enter_context(base.session(a.native,p,plan))
            vanilla=stack.enter_context(base.session(vdir/'vanilla',p))
            captured=infer(dict(req,receipt_oracle='capture'))
            assert captured['state_sha']==gold['state_sha'] and captured['multi']['total_rhs']==gold['rhs_count']
            report={'vanilla':dict(runs=gold['runs'],rhs=gold['rhs_count'],ms=[])}
            for arm in (['live','all','positive'] if a.transfer_only else ARMS):
                v=infer(dict(req,receipt_oracle=arm,audit=True))
                assert 'source_error' not in v,(case,arm,v.get('source_error'))
                row=base.summarize(v,gold)
                row.pop('rows');row.pop('work')
                row['verified_source_rhs']=row.pop('neural_rhs')
                row['online_root_rhs']=v['online_neural_rhs']
                report[arm]=row
                row.update(tape=v['receipt_oracle'],raw_multi=v['multi']['counts']['raw_tuples'],single_checked=v['single']['work'][2])
                if arm!='live':
                    for field in ('single_winners','multi_winners','cells','state_sha','root_parents','root_ids','nested_ids','rhs','direct_cells'):
                        assert row[field]==report['live'][field],(case,arm,field)
                if arm=='all':
                    for field in ('raw','multi','commits','physical','children','wire_hash'):
                        assert row[field]==report['live'][field],(case,arm,field)
                if arm in ('all','positive'):assert row['online_root_rhs']==0
                if arm=='live':assert row['online_root_rhs']==gold['rhs_count']
                del v
            if not a.transfer_only:
                assert report['single']['online_root_rhs']+report['multi']['online_root_rhs']==gold['rhs_count']
            if case==a.cases[0]:
                bad=infer(dict(req,receipt_oracle='site-fault'))
                assert 'source site mismatch' in bad.get('source_error',''),bad.get('source_error')
                report['live']['wrong_site_rejected']=True
                stale=infer(dict(req,receipt_oracle='version-fault'))
                assert 'oracle source version rejected' in stale.get('source_error',''),stale.get('source_error')
                report['live']['wrong_version_rejected']=True
            names=list(report)
            for i in range(1+a.repeats):
                order=names[i%len(names):]+names[:i%len(names)]
                for arm in order if i%2 else reversed(order):
                    v=vanilla({}) if arm=='vanilla' else infer(dict(req,receipt_oracle=arm))
                    assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs']
                    if arm!='vanilla':assert v['online_neural_rhs']==report[arm]['online_root_rhs'] and v['root_recipe']['allocated']==report['live']['root_allocated']
                    if i:report[arm]['ms'].append(v['ms'])
            for row in report.values():row['median_ms']=median(row['ms'])
        results[case]=report
        (a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
        print(case,[(k,round(v['median_ms'],2),v.get('online_root_rhs')) for k,v in report.items()],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','conjugate-gradient','3mm'])
    p.add_argument('--transfer-only',action='store_true')
    p.add_argument('--seed',type=int,default=1703);p.add_argument('--repeats',type=int,default=4)
    measure(p.parse_args())

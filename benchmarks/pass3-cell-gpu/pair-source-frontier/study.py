"""Ablate direct evaluation, cached derived ports and indexed neural pair selection on full Pass 3."""
import argparse
from contextlib import ExitStack
import importlib.util,json
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('source_pair_profile',HERE/'profile.py')
common=importlib.util.module_from_spec(spec);spec.loader.exec_module(common)
base=common.base

def choices(req,a):
    cfg={'off':req}
    for arm,(mode,cache) in {'early':(1,False),'cached':(1,True),'indexed':(2,True)}.items():
        if arm in a.arms:cfg[arm]=dict(req,derived_ports=dict(mode=mode,cache=cache))
    return cfg


def inspect(arm,out,q,report):
    q['equations']=out['multi']['equations']
    if arm!='off':
        assert q['equations']['calls'] and q['equations']['numeric_requests']
        if arm!='early' and 'early' in report:
            for f in ('raw','multi','physical','commits','children'):assert q[f]==report['early'][f]


def control(infer,req,gold,report):
    out=infer(dict(req,derived_ports=dict(mode=3),audit=True));q=base.summarize(out,gold)
    for k in ('raw','multi','physical','commits','children'):assert q[k]==report['off'][k]
    report['off']['disabled_plan_calls']=out['multi']['equations']['invalid_receipts']


def study(a,settings=choices,observe=inspect,control_trial=control):
    a.out.mkdir(parents=True,exist_ok=False);results={}
    for case in a.cases:
        p,plan,req=common.config(a,case)
        cfg=settings(req,a)
        vd=a.exp/'compact-vanilla-20261121'
        with base.session(vd/'vanilla-audit',p) as original:gold=original({'audit':True})
        with ExitStack() as stack:
            vanilla=stack.enter_context(base.session(vd/'vanilla',p));infer=stack.enter_context(base.session(a.native,p,plan))
            report={'vanilla':dict(runs=gold['runs'],rhs=gold['rhs_count'],ms=[])}
            for arm,request in cfg.items():
                v=infer(dict(request,audit=True));q=base.summarize(v,gold);q.pop('rows');q.pop('work')
                m=v['multi'];q.update(equations=m['equations'],counts=m['counts'])
                if arm!='off':
                    for k in ('single_winners','multi_winners','root_parents','root_ids','nested_ids','cells','rhs','direct_cells'):
                        assert q[k]==report['off'][k],(case,arm,k)
                report[arm]=q;del v
            if case==a.cases[0] and control_trial:control_trial(infer,req,gold,report)
            names=list(report)
            for trial in range(1+a.repeats):
                pos=trial%len(names);seq=names[pos:]+names[:pos]
                for arm in seq if trial%2 else reversed(seq):
                    v=vanilla({}) if arm=='vanilla' else infer(dict(cfg[arm],audit=False))
                    assert v['runs']==gold['runs'] and v['state_sha']==gold['state_sha']
                    if arm!='vanilla':assert v['root_recipe']['allocated']==report[arm]['root_allocated']
                    if trial:report[arm]['ms'].append(v['ms'])
            for row in report.values():row['median_ms']=median(row['ms'])
        results[case]=report;(a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
        print(case,[(k,round(v['median_ms'],2),v.get('counts',{}).get('raw_tuples')) for k,v in report.items()],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','jacobi-1d','conjugate-gradient'])
    p.add_argument('--arms',nargs='+',choices=('early','cached','indexed'),default=['early','cached','indexed'])
    p.add_argument('--repeats',type=int,default=6);study(p.parse_args())

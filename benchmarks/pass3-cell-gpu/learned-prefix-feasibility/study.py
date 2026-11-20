"""Check prefix-domain pruning before timing complete resident CPU inference."""
import argparse
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('integrated_cpu_policy',HERE.parent/'integrated-cpu-policy/measure.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)

SHAPES={'off':None,'future1':(1,True,False),'future2':(2,True,False),
        'fresh2':(2,False,True),'both2':(2,True,True),'both3':(3,True,True)}


def settings(name,a):
    s=SHAPES[name]
    if s is None:return {}
    columns,existence,freshness=s
    return dict(forward=dict(columns=columns,budget=a.bytes,existence=existence,
                             freshness=freshness,min_candidates=a.min_candidates))


def run(a):
    a.out.mkdir(parents=True,exist_ok=False);result={}
    admission=base.read(HERE.parent/'single-signature-frontier/admission.json')['parameters']
    for case in a.cases:
        prog,plan,_,request=base.setup(a,case)
        configured=base.query(request,'all',admission)
        binary=a.exp/'compact-vanilla-20261121'
        with base.session(binary/'vanilla-audit',prog) as original:gold=original({'audit':True})
        with ExitStack() as ctx:
            infer=ctx.enter_context(base.session(a.native,prog,plan))
            source=ctx.enter_context(base.session(binary/'vanilla',prog))
            report={'vanilla':dict(runs=gold['runs'],rhs=gold['rhs_count'],ms=[])}
            for arm in a.arms:
                delta=settings(arm,a)
                out=infer(dict(configured,**delta,audit=True))
                v=base.summarize(out,gold)
                assert out['multi']['counts']['exhausted']==0
                v.update(guards=out['multi']['forward'],counts=out['multi']['counts'],
                         raw_packets=out['multi']['counts']['raw_tuples'])
                v.pop('rows');v.pop('work')
                if arm=='off':reference=v
                else:
                    for key in ('single_winners','multi_winners','root_parents','root_ids','nested_ids','cells','state_sha','rhs','direct_cells'):
                        assert v[key]==reference[key],(case,arm,key)
                report[arm]=v
            if case==a.cases[0]:
                delta=settings('both2',a)
                out=infer(dict(configured,forward=dict(delta['forward'],stale_control=True),audit=True))
                control=base.summarize(out,gold)
                for key in ('raw','multi','commits','physical','children','cells'):assert control[key]==reference[key]
                assert out['multi']['forward']['rejected_receipts']>0
                report['off']['invalid_control']=out['multi']['forward']['rejected_receipts']
            names=list(report)
            for lap in range(a.repeats+1):
                i=lap%len(names);seq=names[i:]+names[:i]
                for arm in seq if lap%2 else seq[::-1]:
                    out=source({}) if arm=='vanilla' else infer(dict(configured,**settings(arm,a),audit=False))
                    assert out['state_sha']==gold['state_sha'] and out['runs']==gold['runs']
                    if arm!='vanilla':assert out['root_recipe']['allocated']==report[arm]['root_allocated']
                    if lap:report[arm]['ms'].append(out['ms'])
            for v in report.values():v['median_ms']=median(v['ms'])
        result[case]=report
        (a.out/'results.json').write_text(json.dumps(result,indent=1)+'\n')
        print(case,[(k,round(v['median_ms'],2),v.get('raw_packets')) for k,v in report.items()],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--arms',nargs='+',choices=SHAPES,default=list(SHAPES))
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','jacobi-1d'])
    p.add_argument('--repeats',type=int,default=6);p.add_argument('--bytes',type=int,default=4<<20)
    p.add_argument('--min-candidates',type=int,default=8);a=p.parse_args()
    assert a.arms[0]=='off';run(a)

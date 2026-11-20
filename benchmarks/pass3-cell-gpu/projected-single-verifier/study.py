"""Isolate compiled single-parent operand addressing with the same multi-parent proposer."""
import argparse
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('integrated_cpu_policy',HERE.parent/'integrated-cpu-policy/measure.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
COLUMNS=dict(columns=2,budget=4<<20,existence=True,freshness=True,min_candidates=8)
ARMS={'off':{},'forward':dict(forward=COLUMNS),'projection':dict(forward=COLUMNS,projected_checks=1),
      'canonical':dict(forward=COLUMNS,projected_checks=2)}


def run(a):
    a.out.mkdir(parents=True,exist_ok=False);results={}
    admission=base.read(HERE.parent/'single-signature-frontier/admission.json')['parameters']
    for case in a.cases:
        prog,plan,_,parent=base.setup(a,case);req=base.query(parent,'all',admission)
        cpu=a.exp/'compact-vanilla-20261121'
        with base.session(cpu/'vanilla-audit',prog) as gold_run:gold=gold_run({'audit':True})
        with ExitStack() as stack:
            plain=stack.enter_context(base.session(cpu/'vanilla',prog))
            infer=stack.enter_context(base.session(a.native,prog,plan))
            arms={'vanilla':dict(ms=[],runs=gold['runs'],rhs=gold['rhs_count'])}
            for name,delta in ARMS.items():
                out=infer(dict(req,**delta,audit=True))
                v=base.summarize(out,gold);v.pop('work');v.pop('rows')
                v.update(projection=out['single']['adaptive_rows']['projection'],
                         single_work=out['single']['work'],raw_packets=out['multi']['counts']['raw_tuples'])
                if name!='off':
                    for f in ('single_winners','multi_winners','root_parents','root_ids','nested_ids','cells','rhs','direct_cells'):
                        assert v[f]==arms['off'][f],(case,name,f)
                if name in ('projection','canonical'):
                    assert v['projection']['attempts'] and v['projection']['successes']
                    for f in ('raw','multi','commits','physical','children','single_work'):assert v[f]==arms['forward'][f],(case,name,f)
                arms[name]=v
            names=list(arms)
            for lap in range(a.repeats+1):
                i=lap%len(names);seq=names[i:]+names[:i]
                for name in seq if lap%2 else reversed(seq):
                    out=plain({}) if name=='vanilla' else infer(dict(req,**ARMS[name],audit=False))
                    assert out['state_sha']==gold['state_sha'] and out['runs']==gold['runs']
                    if name!='vanilla':assert out['root_recipe']['allocated']==arms[name]['root_allocated']
                    if lap:arms[name]['ms'].append(out['ms'])
            for arm in arms.values():arm['median_ms']=median(arm['ms'])
        results[case]=arms;(a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
        print(case,[(n,round(v['median_ms'],2),v.get('projection',{}).get('attempts')) for n,v in arms.items()],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','jacobi-1d','conjugate-gradient'])
    p.add_argument('--repeats',type=int,default=6);run(p.parse_args())

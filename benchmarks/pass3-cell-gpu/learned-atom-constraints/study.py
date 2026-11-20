"""Attribute actual parent failures and test whether local learned port constraints can prune them."""
import argparse
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('integrated_policy',HERE.parent/'integrated-cpu-policy/measure.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)

ARMS={'one':(1,0),'local':(1,1),'cached':(1,2),'two':(2,0),'two-cached':(2,2),'three':(3,0),'three-cached':(3,2)}


def study(a):
    a.out.mkdir(parents=True,exist_ok=False);result={}
    admission=base.read(HERE.parent/'single-signature-frontier/admission.json')['parameters']
    for case in a.cases:
        prog,plan,_,request=base.setup(a,case);req=base.query(request,'all',admission)
        req['forward']=dict(columns=2,budget=4<<20,existence=True,freshness=True,min_candidates=8)
        configs={}
        for name in a.arms:
            n,local=ARMS[name];views='' if n==1 else f'{n}x'
            configs[name]=dict(req,multi_mode=f'rowdeltapairguardstackseal{views}learned',atom_constraints=local)
        cpu=a.exp/'compact-vanilla-20261121'
        with base.session(cpu/'vanilla-audit',prog) as ref:gold=ref({'audit':True})
        with ExitStack() as stack:
            orig=stack.enter_context(base.session(cpu/'vanilla',prog));engine=stack.enter_context(base.session(a.native,prog,plan))
            arms={'vanilla':dict(ms=[],rhs=gold['rhs_count'],runs=gold['runs'])}
            for name,config in configs.items():
                out=engine(dict(config,audit=True));v=base.summarize(out,gold)
                v.pop('rows');v.pop('work');m=out['multi'];v.update(atom=m['atom_constraints'],counts=m['counts'])
                assert not m['counts']['exhausted'] and sum(v['atom'][k] for k in ('failure_header','failure_cross','failure_local','failure_literal'))==m['counts']['raw_parent_rejects']
                if name!='one':
                    for f in ('single_winners','multi_winners','root_parents','root_ids','nested_ids','cells','rhs','direct_cells'):
                        assert v[f]==arms['one'][f],(case,name,f)
                if name=='cached' and 'local' in arms:
                    for f in ('raw','multi','commits','children','physical'):assert v[f]==arms['local'][f]
                arms[name]=v
            names=list(arms)
            for lap in range(1+a.repeats):
                k=lap%len(names);seq=names[k:]+names[:k]
                for name in seq if lap%2==0 else reversed(seq):
                    v=orig({}) if name=='vanilla' else engine(dict(configs[name],audit=False))
                    assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs']
                    if name!='vanilla': assert v['root_recipe']['allocated']==arms[name]['root_allocated']
                    if lap:arms[name]['ms'].append(v['ms'])
            for v in arms.values():v['median_ms']=median(v['ms'])
        result[case]=arms;(a.out/'results.json').write_text(json.dumps(result,indent=1)+'\n')
        print(case,[(k,round(v['median_ms'],2),v.get('counts',{}).get('raw_tuples')) for k,v in arms.items()],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','jacobi-1d','conjugate-gradient'])
    p.add_argument('--arms',choices=ARMS,nargs='+',default=list(ARMS))
    p.add_argument('--repeats',type=int,default=6);a=p.parse_args();assert a.arms[0]=='one';study(a)

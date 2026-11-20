"""Separate narrow evidence, precomputed physical projections and stronger learned evidence."""
import argparse
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('integrated_policy',HERE.parent/'integrated-cpu-policy/measure.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
MODES={'one':(1,False,False,1),'two':(2,False,False,1),'primary':(2,True,False,1),
       'columns':(2,False,True,1),'both':(2,True,True,1),'evidence':(2,True,False,2),
       'full':(2,True,True,2),'three-full':(3,True,True,3)}


def study(a):
    a.out.mkdir(parents=True,exist_ok=False);result={}
    admission=base.read(HERE.parent/'single-signature-frontier/admission.json')['parameters']
    for case in a.cases:
        prog,plan,_,request=base.setup(a,case);req=base.query(request,'all',admission)
        req.update(forward=dict(columns=2,budget=4<<20,existence=True,freshness=True,min_candidates=8),atom_constraints=2)
        configs={}
        for name in a.arms:
            n,primary,cols,ev=MODES[name];cfg=dict(req)
            if n>1:cfg['multi_mode']=cfg['multi_mode'].replace('seallearned',f'seal{n}xlearned')
            if primary or cols:cfg['tiered_ports']=dict(primary=primary,columns=cols,evidence_views=ev,bytes=1<<20)
            configs[name]=cfg
        cpu=a.exp/'compact-vanilla-20261121'
        with base.session(cpu/'vanilla-audit',prog) as orig:gold=orig({'audit':True})
        with ExitStack() as stack:
            orig=stack.enter_context(base.session(cpu/'vanilla',prog));infer=stack.enter_context(base.session(a.native,prog,plan))
            rows={'vanilla':dict(ms=[],runs=gold['runs'],rhs=gold['rhs_count'])}
            for name,cfg in configs.items():
                out=infer(dict(cfg,audit=True));m=out['multi'];v=base.summarize(out,gold);v.pop('work');v.pop('rows')
                v.update(tier=m['tier'],forward=m['forward'],counts=m['counts'],atom=m['atom_constraints'])
                if name!=a.arms[0]:
                    for f in ('root_parents','root_ids','single_winners','multi_winners','nested_ids','cells','direct_cells','rhs'):
                        assert v[f]==rows[a.arms[0]][f],(name,case,f)
                if name in ('primary','columns','both') and 'two' in rows or name=='full' and 'evidence' in rows:
                    compare=rows['evidence' if name=='full' else 'two']
                    for f in ('raw','multi','physical','commits','children'):assert v[f]==compare[f],(case,name,f)
                rows[name]=v
            names=list(rows)
            for lap in range(1+a.repeats):
                pos=lap%len(names);seq=names[pos:]+names[:pos]
                for name in seq if lap%2 else reversed(seq):
                    out=orig({}) if name=='vanilla' else infer(dict(configs[name],audit=False))
                    assert out['runs']==gold['runs'] and out['state_sha']==gold['state_sha']
                    if name!='vanilla':assert out['root_recipe']['allocated']==rows[name]['root_allocated']
                    if lap:rows[name]['ms'].append(out['ms'])
            for v in rows.values():v['median_ms']=median(v['ms'])
        result[case]=rows;(a.out/'results.json').write_text(json.dumps(result,indent=1)+'\n')
        print(case,[(k,round(v['median_ms'],2),v.get('counts',{}).get('raw_tuples')) for k,v in rows.items()],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','jacobi-1d','conjugate-gradient'])
    p.add_argument('--arms',nargs='+',choices=MODES,default=list(MODES))
    p.add_argument('--repeats',type=int,default=6);study(p.parse_args())

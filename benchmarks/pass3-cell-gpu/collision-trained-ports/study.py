import argparse
import json
from contextlib import ExitStack
from pathlib import Path
from statistics import median
from common import base,configured,TEST


def run(a):
    a.out.mkdir(parents=True,exist_ok=False);all_results={}
    for case in a.cases:
        prog,plan,req=configured(a,case)
        configs={}
        for name in a.arms:
            cfg=dict(req)
            if name!='one':cfg['multi_mode']=cfg['multi_mode'].replace('seallearned','seal2xlearned')
            if name not in ('one','reuse10'):
                cfg.update(secondary_weights=str(a.model/f'{name}.json'),secondary_codes=str(a.model/f'{name}.bin'))
            configs[name]=cfg
        cpu=a.exp/'compact-vanilla-20261121'
        with base.session(cpu/'vanilla-audit',prog) as source:gold=source({'audit':True})
        with ExitStack() as stack:
            original=stack.enter_context(base.session(cpu/'vanilla',prog));infer=stack.enter_context(base.session(a.build/'session',prog,plan))
            arms={'vanilla':dict(ms=[],rhs=gold['rhs_count'],runs=gold['runs'])}
            for name,cfg in configs.items():
                out=infer(dict(cfg,audit=True));v=base.summarize(out,gold)
                v.pop('work');v.pop('rows');m=out['multi'];v.update(failure=m['atom_constraints'],counts=m['counts'])
                assert v['counts']['exhausted']==0
                if name!='one':
                    for f in ('single_winners','multi_winners','root_parents','root_ids','nested_ids','state_sha','cells','direct_cells'):
                        assert v[f]==arms['one'][f],(case,name,f)
                arms[name]=v
            names=list(arms)
            for lap in range(a.repeats+1):
                i=lap%len(names);seq=names[i:]+names[:i]
                for name in seq if lap%2 else reversed(seq):
                    out=original({}) if name=='vanilla' else infer(dict(configs[name],audit=False))
                    assert out['state_sha']==gold['state_sha'] and out['runs']==gold['runs']
                    if name!='vanilla':assert out['root_recipe']['allocated']==arms[name]['root_allocated']
                    if lap:arms[name]['ms'].append(out['ms'])
            for v in arms.values():v['median_ms']=median(v['ms'])
        all_results[case]=arms;(a.out/'results.json').write_text(json.dumps(all_results,indent=1)+'\n')
        print(case,[(n,round(v['median_ms'],2),v.get('counts',{}).get('raw_tuples')) for n,v in arms.items()],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','build','model','out'):p.add_argument(k,type=Path)
    p.add_argument('--repeats',type=int,default=6);p.add_argument('--cases',nargs='+',choices=TEST,default=TEST)
    p.add_argument('--arms',nargs='+',choices=('one','reuse10','initial2','uniform2','hard2','hard4','hard8'),default=['one','initial2','uniform2','hard2','hard4','hard8','reuse10'])
    a=p.parse_args();assert a.arms[0]=='one';run(a)

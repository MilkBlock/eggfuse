"""Prepare column views at rule entry, and compare unchanged sealed proof streams."""
import argparse
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('integrated_policy',HERE.parent/'integrated-cpu-policy/measure.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)


def run(a):
    a.out.mkdir(parents=True,exist_ok=False);result={}
    admission=base.read(HERE.parent/'single-signature-frontier/admission.json')['parameters']
    modes={'baseline':0,'hoist':1,'columns':2,'both':3}
    for case in a.cases:
        prog,plan,_,request=base.setup(a,case)
        req=base.query(request,'all',admission)
        req['forward']=dict(columns=2,budget=4<<20,existence=True,freshness=True,min_candidates=8)
        cfg={name:dict(req,prepared=dict(mode=mode,bytes=1<<20)) if mode else req for name,mode in modes.items()}
        cpu=a.exp/'compact-vanilla-20261121'
        with base.session(cpu/'vanilla-audit',prog) as native:gold=native({'audit':True})
        with ExitStack() as stack:
            plain=stack.enter_context(base.session(cpu/'vanilla',prog))
            trained=stack.enter_context(base.session(a.native,prog,plan))
            rows={'vanilla':dict(ms=[],rhs=gold['rhs_count'],runs=gold['runs'])}
            for name,config in cfg.items():
                out=trained(dict(config,audit=True));v=base.summarize(out,gold)
                v.pop('work');v.pop('rows');v.update(prepared=out['multi']['prepared'],raw_packets=out['multi']['counts']['raw_tuples'])
                if name!='baseline':
                    for key in ('raw','physical','commits','children','multi','single_winners','multi_winners','cells','root_parents','root_ids','nested_ids'):
                        assert v[key]==rows['baseline'][key],(case,name,key)
                rows[name]=v
            names=list(rows)
            for lap in range(a.repeats+1):
                i=lap%len(names);seq=names[i:]+names[:i]
                for name in seq if lap%2 else reversed(seq):
                    out=plain({}) if name=='vanilla' else trained(dict(cfg[name],audit=False))
                    assert out['state_sha']==gold['state_sha'] and out['runs']==gold['runs']
                    if name!='vanilla':assert out['root_recipe']['allocated']==rows[name]['root_allocated']
                    if lap:rows[name]['ms'].append(out['ms'])
            for v in rows.values():v['median_ms']=median(v['ms'])
        result[case]=rows;(a.out/'results.json').write_text(json.dumps(result,indent=1)+'\n')
        print(case,{n:round(v['median_ms'],2) for n,v in rows.items()},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','jacobi-1d','conjugate-gradient'])
    p.add_argument('--repeats',type=int,default=6);run(p.parse_args())

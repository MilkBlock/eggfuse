"""Verify conservative reverse root seeding against the identical forward proof and raw stream."""
import argparse
from contextlib import ExitStack
import importlib.util,json
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('integrated_policy',HERE.parent/'integrated-cpu-policy/measure.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)


def run(a):
    a.out.mkdir(parents=True,exist_ok=False);results={}
    admission=base.read(HERE.parent/'single-signature-frontier/admission.json')['parameters']
    for case in a.cases:
        prog,plan,_,req=base.setup(a,case);req=base.query(req,'all',admission)
        req.update(forward=dict(columns=2,budget=4<<20,existence=True,freshness=True,min_candidates=8),
                   atom_constraints=2,multi_mode=req['multi_mode'].replace('seallearned','seal2xlearned'),
                   tiered_ports=dict(primary=True,columns=True,evidence_views=1,bytes=1<<20))
        cfg={'forward':req}
        for label,minimum,pct in [('sparse',64,20),('middle',32,50),('broad',16,80)]:
            cfg[label]=dict(req,reverse_fresh=dict(min_rows=minimum,percent=pct,budget=4<<20))
        vd=a.exp/'compact-vanilla-20261121'
        with base.session(vd/'vanilla-audit',prog) as ref:gold=ref({'audit':True})
        with ExitStack() as stack:
            vanilla=stack.enter_context(base.session(vd/'vanilla',prog));learn=stack.enter_context(base.session(a.native,prog,plan))
            arms={'vanilla':dict(ms=[],runs=gold['runs'],rhs=gold['rhs_count'])}
            for name,delta in cfg.items():
                out=learn(dict(delta,audit=True));v=base.summarize(out,gold);v.pop('work');v.pop('rows')
                m=out['multi'];v.update(domain=m['root_domain'],raw_packets=m['counts']['raw_tuples'])
                if name!='forward':
                    for f in ('raw','multi','physical','commits','children','cells','root_ids','single_winners','multi_winners','nested_ids'):
                        assert v[f]==arms['forward'][f],(case,name,f)
                    assert v['domain']['used']>0
                arms[name]=v
            names=list(arms)
            for lap in range(a.repeats+1):
                pos=lap%len(names);seq=names[pos:]+names[:pos]
                for name in seq if lap%2 else reversed(seq):
                    out=vanilla({}) if name=='vanilla' else learn(dict(cfg[name],audit=False))
                    assert out['state_sha']==gold['state_sha'] and gold['runs']==out['runs']
                    if name!='vanilla':assert out['root_recipe']['allocated']==arms[name]['root_allocated']
                    if lap:arms[name]['ms'].append(out['ms'])
            for v in arms.values():v['median_ms']=median(v['ms'])
        results[case]=arms;(a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
        print(case,[(k,round(v['median_ms'],2),v.get('domain',{}).get('used')) for k,v in arms.items()],flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--repeats',type=int,default=6)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','jacobi-1d','conjugate-gradient']);run(p.parse_args())

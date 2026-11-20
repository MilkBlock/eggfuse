"""Factor source key ordering on verified batches; exact stable source ownership is the acceptance test."""
import argparse,importlib.util,json
from contextlib import ExitStack
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('source_profile',HERE.parent/'pair-source-frontier/profile.py')
common=importlib.util.module_from_spec(spec);spec.loader.exec_module(common)
base=common.base
MODES={'source':0,'direct':1,'ordinal':2,'varying':3,'prefix':4}

def run(a):
    a.out.mkdir(parents=True,exist_ok=False);results={}
    for case in a.cases:
        p,plan,req=common.config(a,case);req.update(derived_ports=dict(mode=1,cache=True))
        vd=a.exp/'compact-vanilla-20261121'
        with base.session(vd/'vanilla-audit',p) as ref:gold=ref({'audit':True})
        with ExitStack() as s:
            vanilla=s.enter_context(base.session(vd/'vanilla',p));infer=s.enter_context(base.session(a.native,p,plan))
            report={'vanilla':dict(ms=[],runs=gold['runs'],rhs=gold['rhs_count'])};cfg={}
            for name in a.arms:
                cfg[name]=dict(req,binding_order=dict(mode=MODES[name],min=4))
                v=infer(dict(cfg[name],audit=True));q=base.summarize(v,gold);q.pop('rows');q.pop('work')
                q['order']=v['binding_order']
                if name!='source':
                    assert q['order']['matched_layouts']>0
                    for f in ('raw','multi','physical','commits','children','cells','root_ids','single_winners','multi_winners','root_parents','nested_ids'):
                        assert q[f]==report['source'][f],(case,name,f)
                # Independent timing diagnostic includes the actual implementation used in this arm.
                measured=infer(dict(req,binding_order=dict(mode=MODES[name],min=4,clock=True),audit=False))
                assert measured['runs']==gold['runs'] and measured['state_sha']==gold['state_sha']
                q['clock_ns']=measured['binding_order']['time_ns']
                report[name]=q;del v
            names=list(report)
            for lap in range(1+a.repeats):
                i=lap%len(names);seq=names[i:]+names[:i]
                for name in seq if lap%2 else reversed(seq):
                    v=vanilla({}) if name=='vanilla' else infer(dict(cfg[name],audit=False))
                    assert v['runs']==gold['runs'] and v['state_sha']==gold['state_sha']
                    if name!='vanilla':assert v['root_recipe']['allocated']==report[name]['root_allocated']
                    if lap:report[name]['ms'].append(v['ms'])
            for r in report.values():r['median_ms']=median(r['ms'])
        results[case]=report;(a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
        print(case,[(k,round(v['median_ms'],2),round(v.get('clock_ns',0)/1e6,2)) for k,v in report.items()],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--arms',nargs='+',choices=MODES,default=list(MODES))
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','jacobi-1d','conjugate-gradient'])
    p.add_argument('--repeats',type=int,default=6);a=p.parse_args();assert a.arms[0]=='source';run(a)

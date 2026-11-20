"""Real counterfactual samples from the same source Run and rule under two complete executions."""
import argparse,json
from pathlib import Path
from statistics import median
from driver import bridge,choices,control


def collect(a):
    a.out.mkdir(parents=True,exist_ok=False)
    rows=[]
    for case in a.cases:
        program,plans,req=bridge.config(a,case)
        _,route=choices(req,a)
        with bridge.parent.base.session(a.exp/'compact-vanilla-20261121/vanilla',program) as baseline:
            gold=baseline({})
        times=[[],[]]
        keys=None
        with bridge.parent.base.session(a.native,program,plans) as infer:
            for i in range(a.repeats+1):
                for mode in ((1,2) if i%2 else (2,1)):
                    out=infer(control(route,mode,True))
                    assert out['runs']==gold['runs'] and out['state_sha']==gold['state_sha']
                    assert out['multi']['total_rhs']==gold['rhs_count']
                    report=out['multi']['route_gate']
                    trace=report['samples']
                    assert len(trace)==report['calls'] and trace and report['choices']==(len(trace) if mode==2 else 0)
                    current=[(run,rid,x) for run,rid,x,_,_ in trace]
                    if keys is None:keys=current
                    assert keys==current
                    assert all(chosen==(mode==2) and ns>0 for _,_,_,chosen,ns in trace)
                    if i:times[mode-1].append([s[-1] for s in trace])
        for k,(run,rid,x) in enumerate(keys):
            rows.append(dict(program=case,run=run,rule=rid,x=x,
                             original_ns=[v[k] for v in times[0]],request_ns=[v[k] for v in times[1]]))
        print(case,len(keys),'paired decisions',flush=True)
    (a.out/'training.json').write_text(json.dumps(rows,separators=(',',':'))+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--seed',type=int,default=1703);p.add_argument('--repeats',type=int,default=5)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','jacobi-1d'])
    collect(p.parse_args())

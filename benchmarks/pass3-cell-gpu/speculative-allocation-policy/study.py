"""Run budget, storage and serial-specific Cell admission on untouched programs."""
import argparse,json
from pathlib import Path
from driver import base,source

def settings(req,a):
    common=base(req)
    def arm(timing,storage,policy,budget=a.cap):
        m=dict(timing=timing,storage=storage,cap=budget)
        if policy in a.model['models'][timing]:
            m.update(policy='score',weights=a.model['models'][timing][policy]['weights'])
        else:m['policy']=policy
        return dict(common,spec_cells=m)
    opts={'off':common,'run-capacity':arm('run','capacity','coverage'),'run-pool':arm('run','pooled','coverage'),
          'run-named':arm('run','named','coverage'),'page-named':arm('page','named','coverage'),
          'run-tight':arm('run','named','coverage',256),'run-previous':arm('run','named','previous'),
          'run-balanced':arm('run','named','balanced')}
    return {k:opts[k] for k in ['off',*a.arms]}

def observe(name,v,q,report):
    q['storage']=v.get('spec_cells',{})
    if isinstance(q['storage'],dict):q['storage'].pop('samples',None)
    if name!='off':
        for k in ('raw','multi','wire_hash','physical','commits','children'):
            assert q[k]==report['off'][k],(name,k)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','policy','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['conjugate-gradient','3mm'])
    p.add_argument('--arms',nargs='+',default=['run-capacity','run-pool','run-named','page-named','run-tight','run-previous','run-balanced'])
    p.add_argument('--cap',type=int,default=8192);p.add_argument('--seed',type=int,default=1703);p.add_argument('--repeats',type=int,default=4)
    a=p.parse_args();a.model=json.loads(a.policy.read_bytes());source.study(a,settings,observe,None)

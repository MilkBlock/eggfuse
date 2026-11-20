"""Hold the co-repair edge fixed; toggle a live reader outside the catalog."""
import argparse,json,subprocess,sys
from pathlib import Path
import numpy as np
from collect import read,call,GPU
from device import execute_case
sys.path.insert(0,str(GPU/'set-memory'))
from check import check

SOURCE="""
(datatype Expr (Atom i64) (Single Expr) (ContextOf Expr) (OtherReader Expr))
(relation Start (i64))
(relation Demand (i64))
(ruleset make)
(ruleset readers)
(ruleset external)
(ruleset merge)
(rule ((Start n)) ((Atom n) (Atom (+ n 1))) :ruleset make)
(rule ((= x (Atom n))) ((Single x) (ContextOf x)) :ruleset readers)
(rule ((Demand 1) (= x (Atom 2))) ((OtherReader x)) :ruleset external)
(rule ((= x (Atom 1)) (= y (Atom 2))) ((union y x)) :ruleset merge)
(Start 1)
(Demand FLAG)
(run-schedule (seq (run make) (run readers) (run external) (run merge) (run readers)))
"""

def main(a):
    a.out.mkdir(parents=True,exist_ok=False)
    result={}
    for flag in (0,1):
        name=f'demand-{flag}';folder=a.out/name;source=a.out/(name+'.egg')
        source.write_text(SOURCE.replace('FLAG',str(flag)))
        call(a.compiler,'compile','--source',source,'--output',folder)
        trial=folder/'plain'
        check(folder/'program.json',trial,a.weights,a.reference/'ports-1703.pt',a.runtime,32)
        for dest,origin in [('input','input'),('reference','cpu'),('device','gpu')]:
            (folder/dest).symlink_to(trial/origin)
        library=[('Atom','Single',0),('Atom','ContextOf',0)]
        r={}
        for lane,cap in [('producer',1),('one',2),('two',3)]:
            data=execute_case(a.out,a.reference,a.weights,name,folder/lane,
                              library if cap>1 else [],3 if cap>1 else 1,cap,count=True,nested=cap==3)
            c=data['co_repair']['counters']
            r[lane]=dict(readers=c[1],notifications=c[2],key_probes=c[7],collision_tests=c[8],collisions=c[9])
        with np.load(folder/'one/owners.npz') as old,np.load(folder/'two/owners.npz') as new:
            np.testing.assert_array_equal(old['first'],new['first'])
        assert r['two']['readers']>r['one']['readers']>0 and r['two']['collisions']==r['producer']['collisions']>0,r
        result[name]=dict(arms=r,exact=read(trial/'gpu/check.json')['acceptance'])
    assert result['demand-1']['arms']['two']['notifications']>result['demand-0']['arms']['two']['notifications']
    (a.out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('compiler','runtime','weights','reference','out'):p.add_argument(k,type=Path)
    main(p.parse_args())

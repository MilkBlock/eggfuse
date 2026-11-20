"""Evaluate a compiled arithmetic port at request time, after preexisting negative guards."""
import argparse,importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('pair_ablation',HERE.parent/'pair-source-frontier/study.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
def choices(req,a):
    cfg={'off':req}
    q=dict(req,derived_ports=dict(mode=1,cache=True))
    for name,n in [('eager',0),('late',1),('requested',2),('direct',3),('memo',4)]:
        if name in a.arms:cfg[name]=dict(q,lazy_equations=n) if n else q
    return cfg

def inspect(name,out,row,prev):
    row.update(lazy=out['multi']['lazy_eq'],equation=out['multi']['equations'])
    if name in ('late','requested','direct','memo'):
        assert row['lazy']['checks']>0
        if name!='late':assert row['lazy']['computed']>0
        if name=='memo':assert row['lazy']['table_hits']>0
        for key in ('raw','commits','physical','multi','children'):
            assert row[key]==prev['eager'][key]

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','jacobi-1d','conjugate-gradient'])
    p.add_argument('--arms',nargs='+',choices=('eager','late','requested','direct','memo'),default=['eager','late','requested','direct','memo'])
    p.add_argument('--repeats',type=int,default=6);a=p.parse_args();assert a.arms[0]=='eager'
    base.study(a,choices,inspect,None)

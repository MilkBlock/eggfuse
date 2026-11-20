"""Measure certified no-binding reuse while the learned stream and ordered winners are frozen."""
import argparse,importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('source_study',HERE.parent/'pair-source-frontier/study.py')
base=importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
MODES={'reference':1,'tables':3,'rows':4,'classes':5,'two-hit':6,'identity':7,'compressed':8,'eager-compressed':9}


def settings(req,a):
    off=dict(req,header_mode=3,derived_ports=dict(mode=1,cache=True),lazy_equations=4)
    return {'off':off,**{n:dict(off,projected_checks=MODES[n]) for n in a.arms}}


def observe(name,out,row,arms):
    row['certificates']=out['single']['adaptive_rows']['result_certificates']
    row['work']=out['single']['work']
    if name not in ('off','reference'):
        w=row['certificates']
        assert w['writes']>0 and w['hits']==w['audited']
        for key in ('raw','multi','physical','commits','children'):
            assert row[key]==arms['off'][key]


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--arms',nargs='+',default=list(MODES)[:5],choices=MODES)
    p.add_argument('--cases',nargs='+',default=['sum-bits','conjugate-gradient','3mm'])
    p.add_argument('--seed',type=int,default=1703);p.add_argument('--repeats',type=int,default=4)
    base.study(p.parse_args(),settings,observe,None)

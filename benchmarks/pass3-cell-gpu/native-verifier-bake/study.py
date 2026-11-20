"""Time the original and generated source verifiers on the same learned parent stream."""
import argparse,importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('source_study',HERE.parent/'pair-source-frontier/study.py')
base=importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
MODES={'projected':1,'shared':3,'all':4}


def settings(req,a):
    off=dict(req,header_mode=3,derived_ports=dict(mode=1,cache=True),lazy_equations=4)
    return {'off':off,**{k:dict(off,projected_checks=m) for k,m in MODES.items()}}


def observe(arm,out,row,groups):
    v=out['single']['adaptive_rows']['projection']
    row['verifier']=v
    if arm in ('shared','all'):
        assert 0<v['native_calls']<=v['attempts'] and v['installed_native']>0
        ref=groups['projected']['verifier']
        for k in ('attempts','root_constraints','point_reads','scalar_ops','successes'):
            assert v[k]==ref[k],(arm,k)
    if arm!='off':
        for k in ('raw','multi','physical','commits','children'):assert row[k]==groups['off'][k]


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','conjugate-gradient','3mm'])
    p.add_argument('--seed',type=int,default=1703);p.add_argument('--repeats',type=int,default=4)
    base.study(p.parse_args(),settings,observe,None)

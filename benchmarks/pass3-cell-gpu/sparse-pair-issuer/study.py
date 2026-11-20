"""Avoid full source-wide preparation when only new rows can contribute."""
from pathlib import Path
import argparse,importlib.util
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('paired_native',HERE.parent/'pair-source-frontier/study.py')
original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)


def choices(req,a):
    baseline=dict(req,derived_ports=dict(mode=1,cache=True))
    cfg={'off':baseline}
    for arm,mode,minimum,ratio in [('epochs',1,32,1),('narrow',2,32,1),('mixed',3,32,1),('selective',3,128,4)]:
        if arm in a.arms:cfg[arm]=dict(baseline,sparse_pair=dict(mode=mode,min_rows=minimum,ratio=ratio))
    return cfg


def inspect(arm,out,q,report):
    q['sparse']=out['multi']['sparse_pairs']
    if arm!='off':
        for f in ('raw','multi','physical','commits','children'):assert q[f]==report['off'][f],(arm,f)
        assert q['sparse']['unneeded_epoch_sorts']>0


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','jacobi-1d','conjugate-gradient'])
    p.add_argument('--arms',nargs='+',choices=('epochs','narrow','mixed','selective'),default=['epochs','narrow','mixed','selective'])
    p.add_argument('--repeats',type=int,default=6);original.study(p.parse_args(),choices,inspect,None)

"""Keep the same source model and repair order while changing persistent reverse-edge storage."""
import argparse,importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('source_trials',HERE.parent/'pair-source-frontier/study.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
MODES={'small':1,'empty':2,'owner':3,'inline':4,'hybrid':5,'derived':6,'diff':7}


def settings(req,a):
    off=dict(req,header_mode=3,derived_ports=dict(mode=1,cache=True),lazy_equations=4,multi_page_tuples=8192)
    return {'off':dict(off,owner_directory=0),**{n:dict(off,owner_directory=MODES[n]) for n in a.arms}}


def observe(arm,out,row,previous):
    t=out['owner_directory'];row['directory']=t
    assert t['logical_edges']==t['tree_edges']+t['implicit_self']+t['inline_single']+t['forward_derived']
    if arm!='off':
        ref=previous['off']['directory']
        assert t['work']['domain_audits']>0
        for k in ('logical_edges','unions','repairs'):assert t[k]==ref[k]
        for k in ('raw','multi','physical','commits','children'):assert row[k]==previous['off'][k]


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','3mm'])
    p.add_argument('--arms',nargs='+',choices=MODES,default=list(MODES)[:5])
    p.add_argument('--seed',type=int,default=1703);p.add_argument('--repeats',type=int,default=4)
    base.study(p.parse_args(),settings,observe,None)

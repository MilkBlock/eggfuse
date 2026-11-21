"""Seal all model proposals for a rule wave before any of that wave's exact validators execute."""
import argparse,importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('paired_wave',HERE.parent/'pair-source-frontier/study.py')
parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)

def configure(req,a):
    off=dict(req,header_mode=3,derived_ports={'mode':1,'cache':True},lazy_equations=4,multi_page_tuples=8192)
    return {'off':off,**{n:dict(off,proposal_wave=w) for n,w in [('one',1),('eight',8),('run',65536)]}}

def observe(name,out,q,rows):
    w=out['multi']['wave'];q['wave']=w
    q['model_scores']=out['single']['adaptive_rows']['decision_digest']
    if name!='off':
        assert w['waves']>0 and w['single_sets']==w['verified_single_sets'] and w['multi_sets']==w['validated_multi_sets']
        for k in ('raw','multi','wire_hash','physical','commits','children','model_scores'):assert q[k]==rows['off'][k],(name,k)
        if name!='one':assert w['mixed_waves']>0 and w['peak_rules']>1

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','conjugate-gradient','3mm'])
    p.add_argument('--repeats',type=int,default=4);p.add_argument('--seed',type=int,default=1703)
    parent.study(p.parse_args(),configure,observe,None)

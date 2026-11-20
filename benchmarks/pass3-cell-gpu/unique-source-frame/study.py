"""Copyable vs uniquely owned frame updates under the frozen ordered graph contract."""
from pathlib import Path
import argparse,importlib.util
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('paired_native',HERE.parent/'pair-source-frontier/study.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)

def choices(req,a):
    q=dict(req,derived_ports=dict(mode=1,cache=True))
    cfg={'off':q}
    for name,mode,hold in [('move',1,False),('edit',2,False),('held-reader',2,True)]:
        if name in a.arms:cfg[name]=dict(q,edit_frames=dict(mode=mode,hold_control=hold))
    return cfg

def inspect(name,out,v,arms):
    m=out['multi'];v.update(edits=m['frame_edits'],deltas=m['delta_stats'])
    if name!='off':
        for f in ('raw','multi','physical','commits','children'):
            assert v[f]==arms['off'][f],(name,f)
        s=v['edits']
        if name=='held-reader':assert s['copy_fallback'] and not s['updates']
        else:assert s['updates'] and s['checked_source_rows'] and s['retained_without_clone']
        if name=='edit':assert s['in_place']>0

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','jacobi-1d','conjugate-gradient'])
    p.add_argument('--arms',nargs='+',choices=('move','edit','held-reader'),default=['move','edit','held-reader'])
    p.add_argument('--repeats',type=int,default=6);base.study(p.parse_args(),choices,inspect,None)

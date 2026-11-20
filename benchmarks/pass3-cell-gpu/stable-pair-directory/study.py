"""Compare signed two-parent source postings rebuilt or updated from ChangeBatch."""
import argparse,importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('native_equation_trial',HERE.parent/'pair-source-frontier/study.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
def choices(req,a):
    q=dict(req,derived_ports=dict(mode=1,cache=True))
    cfg={'off':q}
    for arm,mode,ratio,n in [('rebuild',1,1,64),('patched',2,1,64),('selective',2,4,128),('broad',2,0,16),('snapshot',3,1,64)]:
        if arm in a.arms:cfg[arm]=dict(q,stable_dirs=dict(mode=mode,min_rows=n,ratio=ratio,bytes=8<<20))
    return cfg

def inspect(name,out,row,prev):
    row['directory']=out['multi']['stable_dirs']
    if name!='off':
        for f in ('raw','physical','commits','multi','children'):assert row[f]==prev['off'][f],(name,f)
        assert row['directory']['activations'] and row['directory']['audit_rows'] and row['directory']['peak_charge']<=8<<20
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','jacobi-1d','conjugate-gradient'])
    p.add_argument('--arms',nargs='+',choices=('rebuild','patched','selective','broad','snapshot'),default=['rebuild','patched','selective','broad'])
    p.add_argument('--repeats',type=int,default=6);base.study(p.parse_args(),choices,inspect,None)

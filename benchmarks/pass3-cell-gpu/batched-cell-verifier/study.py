"""Execute the suffix as a verified page program with static parent-to-operand connections."""
import argparse,importlib.util,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('cohorts',HERE.parent/'page-premise-programs/study.py')
group=importlib.util.module_from_spec(spec);spec.loader.exec_module(group)
MODES={'prepared':4,'register':7,'register-key':8,'port':9}


def settings(req,a):
    off=dict(req,header_mode=3,derived_ports={'mode':1,'cache':True},lazy_equations=4,multi_page_tuples=a.page_size)
    return {'off':off,**{n:dict(off,page_premises=MODES[n]) for n in a.arms}}


def observe(name,out,row,prior):
    group.observe(name,out,row,prior)
    b=out['multi']['blocks'];row['block']=b
    if name in ('register','register-key','port'):
        assert b['completed']>0 and b['started']==b['completed']+b['key_misses']+b['stale']+b['guard_failures']
        if name=='port':assert b['parent_port_hits']>0
        if name!='register' and 'register' in prior:
            for f in ('started','completed','stale','key_misses','guard_failures','value_slots'):
                assert b[f]==prior['register']['block'][f]


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','conjugate-gradient','3mm'])
    p.add_argument('--arms',nargs='+',default=list(MODES),choices=MODES)
    p.add_argument('--page-size',type=int,default=8192);p.add_argument('--seed',type=int,default=1703)
    p.add_argument('--repeats',type=int,default=4)
    group.source.study(p.parse_args(),settings,observe,None)

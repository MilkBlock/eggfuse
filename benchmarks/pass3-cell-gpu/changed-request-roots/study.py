"""Run reverse activation and optional direct receipt transfer on the frozen parent proposer."""
import argparse
import importlib.util
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
connected=HERE.parent/'connected-request-plans'
sys.path.insert(0,str(connected))
spec=importlib.util.spec_from_file_location('connected_source_workload',connected/'study.py')
bridge=importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
MODES={'point':1,'target':2,'receipt':3,'presence':4}


def settings(req,args):
    off=dict(req,header_mode=3,derived_ports=dict(mode=1,cache=True),lazy_equations=4)
    ordinary=dict(off,connected_requests=args.compiled)
    return {'off':off,'direct':ordinary,**{k:dict(ordinary,wake_roots=MODES[k]) for k in args.arms}}


def observe(arm,out,q,rows):
    q['bridge']=out['multi']['bridges']
    q['wake']=out['multi']['wake']
    if arm in MODES:
        baseline=rows['direct']
        for key in ('raw','multi','commits','physical','children'):
            assert q[key]==baseline[key],(arm,key)
        assert q['wake']['routed_calls']>0
        assert q['wake']['all_roots']-q['wake']['active_roots']==baseline['bridge']['root_rows']-q['bridge']['root_rows']


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('exp','native','out'):
        p.add_argument(key,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','conjugate-gradient'])
    p.add_argument('--arms',nargs='+',choices=MODES,default=list(MODES))
    p.add_argument('--seed',type=int,default=1703)
    p.add_argument('--repeats',type=int,default=4)
    bridge.parent.common.config=bridge.config
    bridge.parent.study(p.parse_args(),settings,observe,None)

"""Measure handoff ownership and ticket lifetime inside the real source Run."""
import argparse
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = spec_from_file_location('source_comparison', HERE.parent/'pair-source-frontier/study.py')
base = module_from_spec(spec)
spec.loader.exec_module(base)
ARMS = {'off':0, 'move':1, 'receipt':2, 'run-tickets':4, 'all':7}

def choices(req, args):
    req=dict(req, header_mode=3, derived_ports={'mode':1,'cache':True}, lazy_equations=4)
    return {name:dict(req, verified_transfer=bits) for name,bits in ARMS.items()}

def inspect(name, out, row, rows):
    row['transfer']=out['verified_transfer']
    row['ticket_peak']=out['multi']['ticket_peak']
    row['ticket_retired']=out['multi']['ticket_retired']
    if name!='off':
        for k in ('raw','physical','commits','multi','children','cells'):
            assert row[k]==rows['off'][k],(name,k)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('exp','native','out'):p.add_argument(name,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','3mm'])
    p.add_argument('--seed',type=int,default=1703)
    p.add_argument('--repeats',type=int,default=4)
    base.study(p.parse_args(),choices,inspect,None)

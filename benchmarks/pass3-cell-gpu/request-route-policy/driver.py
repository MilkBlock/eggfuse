"""Shared paths for the measured connected-request provider and its original proposer."""
import importlib.util
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
connected=HERE.parent/'connected-request-plans'
sys.path.insert(0,str(connected))
spec=importlib.util.spec_from_file_location('connected_parent_inputs',connected/'study.py')
bridge=importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


def choices(req,args):
    off=dict(req,header_mode=3,derived_ports=dict(mode=1,cache=True),lazy_equations=4)
    route=dict(off,connected_requests=args.compiled,wake_roots=4)
    return off,route


def control(r,mode,capture=False,weights=None):
    gate=dict(mode=mode,capture=capture)
    if weights is not None:
        gate['weights']=weights
    return dict(r,request_route_gate=gate)

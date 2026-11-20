"""Audit one completed Cell program with independent ordered CPU observers."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent.parent
def check(program,out,weights,ports,runtime,budget):
    def run(*args):
        subprocess.run([str(a) for a in args],check=True,env=dict(os.environ,PYTORCH_ENABLE_MPS_FALLBACK='0'))
    def py(name,*args):run(sys.executable,HERE/name,*args)
    out.mkdir(parents=True,exist_ok=False)
    image=out/'input';gpu=out/'gpu'
    py('codec.py',program,image);py('lower.py',image/'ingress.json')
    py('run.py',image/'device.json',weights,gpu,'--runs',budget,'--port-weights',ports,'--count-work')
    cpu=out/'cpu';events=out/'events'
    run(runtime,'--program',program,'--output',cpu,'--audit-stages')
    run(runtime,'--program',program,'--output',events,'--audit-events')
    py('events_audit.py',program,image/'ingress.json',gpu,cpu,events,gpu/'ordered.json')
    py('endpoint.py',image/'ingress.json',gpu,cpu,gpu/'check.json','--ordered',gpu/'ordered.json')
    assert json.loads((gpu/'check.json').read_text())['acceptance']=='pass'

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ('program','out','weights','ports','audited_runtime'):parser.add_argument(arg,type=Path)
    parser.add_argument('--budget',type=int,default=96)
    a=parser.parse_args();check(a.program,a.out,a.weights,a.ports,a.audited_runtime,a.budget)

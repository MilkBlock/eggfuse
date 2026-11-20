"""Exercise explicit device exhaustion, without using a host-generated answer."""
import json,subprocess,sys
from pathlib import Path

def check(root,compiler,runtime,weights,ports):
    rule='(rule ((Seed n)) ((ES (set-of (Atom n)))) :ruleset build)'
    src='(datatype Expr (Atom i64))\n(sort S (Set Expr))\n(datatype C (ES S))\n(relation Seed (i64))\n(ruleset build)\n'
    source=root/'capacity.egg';source.write_text(src+rule+'\n'+''.join(f'(Seed {i})\n' for i in range(64))+'(run-schedule (run build))\n')
    artifact=root/'capacity';gpu=Path(__file__).resolve().parents[1]
    subprocess.run([compiler,'compile','--source',source,'--output',artifact],check=True)
    subprocess.run([runtime,'--program',artifact/'program.json','--output',root/'capacity-cpu'],check=True,stdout=subprocess.DEVNULL)
    image=root/'capacity-input'
    subprocess.run([sys.executable,gpu/'codec.py',artifact/'program.json',image],check=True)
    subprocess.run([sys.executable,gpu/'lower.py',image/'ingress.json'],check=True)
    output=root/'capacity-gpu'
    proc=subprocess.run([sys.executable,gpu/'run.py',image/'device.json',weights,output,'--port-weights',ports,'--runs','3'])
    state=json.loads((output/'run.json').read_bytes())
    if proc.returncode!=2 or state['finished'] or state['fault']!=20:raise ValueError('capacity must fail closed')
    return dict(input_slots=64,device_capacity=63,cpu_complete=True,gpu_fault=20,returned_success=False)

"""Compile all workloads, execute only ingress packets on Metal, then audit and profile."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

from source import source, inline_input
from check import check
from timing import measure
from results import summarize
from capacity import check as capacity_check
import json

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]

def reproduce(root,weights,ports):
    root.mkdir(parents=True,exist_ok=False)
    bin=Path(os.environ.get('CARGO_TARGET_DIR',REPO/'target'))/'release'
    def cmd(*args,expected=0,stderr=None):
        p=subprocess.run(list(map(str,args)),cwd=REPO,stderr=stderr)
        if p.returncode!=expected:raise RuntimeError((args,p.returncode,expected))
    cmd('cargo','build','--release','--locked','-p','eggfuse-cell-compiler')
    for name in ('compile_local_source','marker_reference'):
        cmd('cargo','build','--release','--locked','-p','eggfuse-cell-compiler','--example',name)
    cmd('cargo','build','--release','--locked','-p','eggfuse-cell-runtime','--features','slot-transfer-audit')
    audited=root/'audited-runtime';shutil.copyfile(bin/'eggfuse-cell-runtime',audited);audited.chmod(0o700)
    for name in ('full','full-probes','helpers','probes','union','dynamic'):
        src=root/f'{name}.egg'
        if name in ('union','dynamic'):src.write_bytes((HERE/f'{name}.egg').read_bytes())
        else:src.write_text(source('probes' in name,name.startswith('full')))
        cmd(bin/'eggfuse-cell-compiler','compile','--source',src,'--output',root/name)
        check(root/name/'program.json',root/f'study-{name}',weights,ports,audited,1056 if name.startswith('full') else 96)
    value='(Const (Int 2) (TupleT (TCons (StateT) (TNil))) (InFunc "dummy"))'
    post=f'(check (= {inline_input(False).strip()} (Bop (Print) {value} rest)))\n'
    (root/'native-check.egg').write_text((root/'full.egg').read_text()+post)
    cmd(bin/'examples/marker_reference',root/'native-check.egg',root/'native-check.json')
    conflict=(HERE/'union.egg').read_text().replace('(run before) (run alias)','(run before) (run memory-helpers) (run alias)')
    (root/'no-merge.egg').write_text(conflict)
    cmd(bin/'examples/compile_local_source','compile','--source',root/'no-merge.egg','--output',root/'no-merge')
    image=root/'conflict-in'
    cmd(sys.executable,HERE.parent/'codec.py',root/'no-merge/program.json',image)
    cmd(sys.executable,HERE.parent/'lower.py',image/'ingress.json')
    cmd(audited,'--program',root/'no-merge/program.json','--output',root/'conflict-cpu',expected=1)
    cmd(sys.executable,HERE.parent/'run.py',image/'device.json',weights,root/'conflict-gpu','--port-weights',ports,'--runs',12,expected=2)
    control=capacity_check(root,bin/'examples/compile_local_source',audited,weights,ports)
    (root/'capacity.json').write_text(json.dumps(control)+'\n')
    timing=root/'timing'
    measure(root,weights,ports,timing,('full','full-probes','probes','union','dynamic'))
    summarize(root,weights,ports,timing,root/'results.json')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('new_output','address_weights','port_weights'):p.add_argument(k,type=Path)
    a=p.parse_args();reproduce(a.new_output.resolve(),a.address_weights.resolve(),a.port_weights.resolve())

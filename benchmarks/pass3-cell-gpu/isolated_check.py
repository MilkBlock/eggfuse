"""Run with an ingress-only temporary mount layout and reject accesses to experiment/oracle files."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent


def worker(directory,experiment):
    import runpy
    seen=set()
    def hook(event,args):
        if event!='open' or not isinstance(args[0],str):return
        p=Path(args[0]).resolve()
        if p.is_relative_to(experiment):raise RuntimeError(f'online access to experiment directory: {p}')
        if p.parent==directory:seen.add(p.name)
    sys.addaudithook(hook)
    sys.argv=[str(HERE/'run.py'),str(directory/'device.json'),str(directory/'address.pt'),str(directory/'result'),
              '--port-weights',str(directory/'ports.pt'),'--export-only']
    runpy.run_path(sys.argv[0],run_name='__main__')
    (directory/'opened.json').write_text(json.dumps(sorted(seen)))


def check(root,address,out):
    report={}
    for case in ('sum-bits','dot-product'):
        with tempfile.TemporaryDirectory() as td:
            tmp=Path(td)
            for name in ('device.npz','device.json','export-schema.json'):
                shutil.copyfile(root/f'release-input-{case}'/name,tmp/name)
            shutil.copyfile(address,tmp/'address.pt');shutil.copyfile(root/'ports-1703.pt',tmp/'ports.pt')
            subprocess.run([sys.executable,__file__,str(tmp),str(root),str(out),'--worker'],check=True)
            actual=(tmp/'result/state.json').read_bytes()
            if hashlib.sha256(actual).hexdigest()!=hashlib.sha256((root/f'export-{case}/state.json').read_bytes()).hexdigest():
                raise ValueError('isolated final graph changed')
            report[case]=dict(opened=json.loads((tmp/'opened.json').read_text()),export_sha256=hashlib.sha256(actual).hexdigest(),
                              completed=json.loads((tmp/'result/run.json').read_text())['completed'])
    out.write_text(json.dumps(report,indent=1)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('root','address','out'):p.add_argument(k,type=Path)
    p.add_argument('--worker',action='store_true')
    a=p.parse_args()
    if a.worker:worker(a.root.resolve(),a.address.resolve().parent)
    else:check(a.root.resolve(),a.address.resolve(),a.out)

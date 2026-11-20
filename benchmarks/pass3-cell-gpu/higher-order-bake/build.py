"""Compile the checked joint Rust implementation with the request-dependent template overlay."""
import argparse,importlib.util,inspect,json
from pathlib import Path
import subprocess,sys,tempfile
HERE=Path(__file__).resolve().parent
BASE='6c2e1583'


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def build(out):
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)
        folders=['joint-witness','single-witness','ordinary-witness','ordinary-shortlist','joint-merge','joint-root-cells']
        args=['git','archive',BASE,*['benchmarks/pass3-cell-gpu/'+f for f in folders]]
        proc=subprocess.Popen(args,cwd=HERE.parents[2],stdout=subprocess.PIPE)
        subprocess.run(['tar','xf','-','-C',root],stdin=proc.stdout,check=True);proc.stdout.close();assert proc.wait()==0
        folder=root/'benchmarks/pass3-cell-gpu/joint-witness';sys.path.insert(0,str(folder))
        joint=load('base_joint',folder/'build.py');overlay=load('guarded_overlay',HERE/'overlay.py')
        source=inspect.getsource(joint.build).replace('cwd=HERE.parents[2]','cwd=worktree')
        anchor="    target=out/'target'";assert source.count(anchor)==1
        src=source.replace(anchor,'    higher_install(crate)\n'+anchor)
        scope=dict(joint.__dict__,higher_install=overlay.install,worktree=HERE.parents[2])
        exec(compile(src,str(joint.__file__),'exec'),scope)
        scope['build'](out,True,True,True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);a=p.parse_args();build(a.out)

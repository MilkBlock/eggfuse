"""Compile the checked joint Rust implementation with the request-dependent template overlay."""
import argparse,hashlib,importlib.util,inspect,json
from pathlib import Path
import subprocess,sys,tempfile
HERE=Path(__file__).resolve().parent
BASE='6c2e1583'


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def installed_receipt(out):
    """Fingerprint the compiled crate, which may differ from a concurrently edited checkout."""
    src=out/'tree/engine/cell-runtime'
    files=['src/higher.rs','src/stage_spine.rs','src/joint_root.rs','src/single_witness.rs',
           'src/runtime.rs','examples/joint_witness_session.rs']
    if (src/'src/higher_pairs.rs').exists():
        files+=['src/higher_pairs.rs','src/ordinary_witness.rs','src/ordinary_shortlist.rs','src/graph.rs']
    data=json.loads((out/'build.json').read_bytes())
    return dict(installer_revision=BASE,native_revision=data['base'],
                executable_sha256=hashlib.sha256((out/'session').read_bytes()).hexdigest(),
                compiled_files={name:hashlib.sha256((src/name).read_bytes()).hexdigest() for name in files})


def build(out,pairs):
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
        def install_experiment(crate):
            overlay.install(crate)
            if pairs:
                sys.path.insert(0,str(HERE))
                load('branch_overlay',HERE/'pair_overlay.py').install(crate)
        scope=dict(joint.__dict__,higher_install=install_experiment,worktree=HERE.parents[2])
        exec(compile(src,str(joint.__file__),'exec'),scope)
        scope['build'](out,True,True,True)
        (out/'higher-build.json').write_text(json.dumps(installed_receipt(out),indent=1)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);p.add_argument('--pairs',action='store_true');a=p.parse_args();build(a.out,a.pairs)

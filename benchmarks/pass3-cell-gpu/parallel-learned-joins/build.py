"""Link the parallel learned-join issuer into the fixed typed-port production policy."""
import argparse
import importlib.util
import inspect
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
INTEGRATED='cdbe8cf9'
EXTENSIONS=('incremental-neural-index','baked-port-codes','adaptive-row-policy',
    'witness-production-profile','multi-root-pages','transaction-guards',
    'single-signature-frontier','integrated-cpu-policy','learned-prefix-feasibility',
    'projected-single-verifier','prepared-port-blocks','learned-atom-constraints','tiered-port-projections',HERE.name)


def build(out):
    base=Path('benchmarks/pass3-cell-gpu')
    inputs=('joint-witness','ordinary-witness','single-witness','ordinary-shortlist',
            'joint-root-cells','joint-merge',*EXTENSIONS[:-1])
    with tempfile.TemporaryDirectory() as directory:
        tree=Path(directory)
        files=subprocess.check_output(['git','ls-tree','-r','--name-only',INTEGRATED,
            *[str(base/name) for name in inputs]],cwd=REPO,text=True).splitlines()
        files=[f for f in files if f.endswith(('.py','.rs'))]
        archive=subprocess.Popen(['git','archive',INTEGRATED,*files],cwd=REPO,stdout=subprocess.PIPE)
        subprocess.run(['tar','xf','-','-C',tree],stdin=archive.stdout,check=True)
        archive.stdout.close()
        if archive.wait():raise RuntimeError('could not read the pinned integration')
        local=tree/base/HERE.name
        local.mkdir(parents=True)
        for f in ('overlay.py','join.rs','cache.rs'):shutil.copy2(HERE/f,local/f)
        source=tree/base/'joint-witness/build.py'
        sys.path.insert(0,str(source.parent))
        spec=importlib.util.spec_from_file_location('linked_joint',source)
        joint=importlib.util.module_from_spec(spec);spec.loader.exec_module(joint)
        code=inspect.getsource(joint.build).replace('cwd=HERE.parents[2]','cwd=repo')
        scope=dict(joint.__dict__,repo=REPO)
        exec(compile(code,str(source),'exec'),scope)
        scope['build'](out,True,True,True,cli_allocator=True,extensions=EXTENSIONS)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out',type=Path)
    build(parser.parse_args().out)

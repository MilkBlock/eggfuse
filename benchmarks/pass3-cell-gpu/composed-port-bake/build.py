"""Build the composed boundary on the pinned native request-bearing runtime."""
import argparse
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SIGNAL_REVISION = '4e16008a'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def receipt(out):
    data = json.loads((out/'higher-build.json').read_bytes())
    for name in ('composed_boundary.rs','composed_delta.rs','runtime_completion.rs'):
        path=out/'tree/engine/cell-runtime/src'/name
        if path.exists():data['compiled_files']['src/'+name]=hashlib.sha256(path.read_bytes()).hexdigest()
    data['guard_revision'] = SIGNAL_REVISION
    return data


def build(out):
    path = Path('benchmarks/pass3-cell-gpu/higher-order-bake')
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        archive = subprocess.Popen(['git','archive',SIGNAL_REVISION,str(path)], cwd=REPO, stdout=subprocess.PIPE)
        subprocess.run(['tar','xf','-','-C',root], stdin=archive.stdout, check=True)
        archive.stdout.close()
        if archive.wait():
            raise RuntimeError('failed to export pinned conditional runtime')
        prior = load('guard_build', root/path/'build.py')
        composed = load('composed_overlay', HERE/'overlay.py')
        source = inspect.getsource(prior.build)
        source = source.replace('cwd=HERE.parents[2],stdout=', 'cwd=source_repo,stdout=')
        source = source.replace('worktree=HERE.parents[2]', 'worktree=source_repo')
        source = source.replace('overlay.install(crate)', 'overlay.install(crate)\n            composed.install(crate)')
        scope = dict(prior.__dict__, composed=composed, source_repo=REPO)
        exec(compile(source, str(prior.__file__), 'exec'), scope)
        scope['build'](out, False)
    (out/'composed-build.json').write_text(json.dumps(receipt(out),indent=1)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out',type=Path)
    build(parser.parse_args().out)

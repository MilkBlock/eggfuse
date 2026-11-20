"""Preserve compact codegen evidence, including actual Rust object counts, without tracking profiles or binaries."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from pgo_common import DONORS,HERE,file_digest,inputs


def units(folder):
    libs=list(folder.glob('libeggfuse_cell_runtime-*.rlib'))
    if len(libs)!=1:raise ValueError((folder,libs))
    return sum(s.endswith('.rcgu.o') for s in subprocess.check_output(['ar','t',libs[0]],text=True).splitlines())


def tree_digest(tree):
    files=sorted(p for p in tree.rglob('*') if p.is_file())
    fingerprints=[[str(p.relative_to(tree)),file_digest(p)] for p in files]
    return dict(files=len(files),sha256=sha256(json.dumps(fingerprints,separators=(',',':')).encode()).hexdigest())


def archive(a):
    build=json.loads((a.build/'build.json').read_bytes())
    for key,meta in build['binaries'].items():
        meta['runtime_codegen_units']=units(a.build/(key+'-target')/'aarch64-apple-darwin/release/deps')
        assert meta['sha256']==file_digest(a.build/key)
    source=a.exp/'composed-cpu-profile-v1'
    build['original_release']={'learned_runtime_codegen_units':units(source/'target/release/deps'),
                                'learned_sha256':file_digest(source/'session'),
                                'vanilla_sha256':file_digest(a.exp/'compact-vanilla-20261121/vanilla')}
    build['source_trees']={name:tree_digest(tree) for name,tree in [('learned',source/'tree'),('vanilla',a.build/'vanilla-src')]}
    build['source_donors']={}
    for case in DONORS:
        p,plan,req=inputs(a,case)
        build['source_donors'][case]=dict(program_sha256=file_digest(p),plan_sha256=file_digest(plan))
    (HERE/'build-evidence.json').write_text(json.dumps(build,indent=1)+'\n')
    shutil.copyfile(a.study/'results.json',HERE/'results.json')
    shutil.copyfile(a.overlap/'overlap.json',HERE/'overlap.json')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','build','study','overlap'):parser.add_argument(k,type=Path)
    a=parser.parse_args();a.out=a.study;a.seed=1703;archive(a)

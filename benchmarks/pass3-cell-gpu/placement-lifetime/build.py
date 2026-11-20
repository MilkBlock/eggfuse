"""Build the single-threaded native owner-placement lifecycle observer in a private source tree."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

HERE=Path(__file__).resolve().parent


def build(base,out):
    out.mkdir(parents=True,exist_ok=False)
    tree=out/'tree'
    subprocess.run(['cp','-cR',base/'tree',tree],check=True)
    src=tree/'engine/cell-runtime/src'
    prog=src/'program.rs'
    s=prog.read_text()
    anchor='        release!(artifact);'
    if s.count(anchor)!=1:raise ValueError(anchor)
    prog.write_text(s.replace(anchor, """        let mut artifact=self.artifact;
        let before=live_bytes();
        if let Some(m)=artifact.as_object_mut(){drop(m.remove("ownership_fragments"));}
        rows.push(("artifact.ownership_fragments",before-live_bytes()));
        let before=live_bytes();drop(artifact);
        rows.push(("artifact",before-live_bytes()));"""))
    p=src/'old_pair_graph.rs'
    with p.open('a') as f:
        f.write((HERE/'action.rs').read_text())
    p=tree/'tools/cell-compiler/examples/existing_owner_transfer.rs'
    s=p.read_text().split('fn main()')[0]
    p.write_text(s+(HERE/'life.rs').read_text())
    env=dict(os.environ,CARGO_TARGET_DIR=str(out/'target'))
    subprocess.run(['cargo','build','--offline','--locked','--release','-p','eggfuse-cell-compiler',
                    '--features','iterative-bake,sparse-cells,storage-metrics','--example','existing_owner_transfer'],env=env,cwd=tree,check=True)
    shutil.copy2(out/'target/release/examples/existing_owner_transfer',out/'engine')
    inputs=['tools/cell-compiler/examples/existing_owner_transfer.rs','engine/cell-runtime/src/old_pair_graph.rs',
            'engine/cell-runtime/src/graph_storage.rs','engine/cell-runtime/src/program.rs',
            'engine/cell-runtime/src/shared_owner_transfer.rs','Cargo.lock']
    digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    manifest=dict(base={rel:digest(base/'tree'/rel) for rel in inputs},sources={p.name:digest(p) for p in (HERE/'life.rs',HERE/'action.rs',HERE/'build.py')},
                  engine=digest(out/'engine'))
    (out/'build.json').write_text(json.dumps(manifest,indent=1)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('base',type=Path);p.add_argument('out',type=Path)
    a=p.parse_args();build(a.base,a.out)

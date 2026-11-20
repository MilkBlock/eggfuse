"""Bake real multi-member shapes offline on each diagnostic input, plus the checked miniature."""
import argparse
from pathlib import Path
import shutil
import subprocess
import os
HERE=Path(__file__).resolve().parent
if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('build','corpus','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    tree=a.build/'tree'
    shutil.copyfile(HERE/'bake.rs',tree/'tools/cell-compiler/examples/existing_owner_bake.rs')
    subprocess.run(['cargo','build','--locked','--release','--offline','-p','eggfuse-cell-compiler','--features','iterative-bake,sparse-cells,storage-metrics','--example','existing_owner_bake'],cwd=tree,env=dict(os.environ,CARGO_TARGET_DIR=str(a.build/'target')),check=True)
    baker=a.build/'target/release/examples/existing_owner_bake'
    for case in ('fixture','dot-product','stable-argmax'):
        src=HERE/'fixture.egg' if case=='fixture' else a.corpus/case/'program.json'
        if not src.exists():src=a.corpus.parent/'pass3-atlas-integration-20261120'/case/'program.json'
        subprocess.run([baker,src,a.out/case],check=True)

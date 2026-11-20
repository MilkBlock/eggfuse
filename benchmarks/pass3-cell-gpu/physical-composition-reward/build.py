"""Compile a read-only training observer and a zero-Run binding checker in a private pinned tree."""
import argparse
import hashlib
import json
from pathlib import Path
import os
import shutil
import subprocess
HERE=Path(__file__).resolve().parent

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('legacy',type=Path);p.add_argument('out',type=Path);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    # Reflink on APFS; the isolated archive already has the storage trial measurement hooks.
    subprocess.run(['cp','-cR',a.legacy/'legacy',a.out/'tree'],check=True)
    crate=a.out/'tree/tools/cell-compiler'
    dest=crate/'examples/physical_reward.rs'
    shutil.copy2(HERE/'observe.rs',dest)
    env=dict(os.environ,CARGO_TARGET_DIR=str(a.out/'target'))
    subprocess.run(['cargo','build','--offline','--locked','--release','-p','eggfuse-cell-compiler',
                    '--features','iterative-bake,sparse-cells,storage-metrics','--example','physical_reward'],
                   cwd=a.out/'tree',env=env,check=True)
    shutil.copy2(a.out/'target/release/examples/physical_reward',a.out/'observe')
    names={'observer':a.out/'observe','driver':a.legacy/'target/release/examples/online_storage_trial'}
    (a.out/'build.json').write_text(json.dumps({k:hashlib.sha256(f.read_bytes()).hexdigest() for k,f in names.items()},indent=1)+'\n')

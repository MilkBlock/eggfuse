import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from patch import HERE,install

ROOT=HERE.parents[2]

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False);repo=a.out/'workspace';repo.mkdir()
    shutil.copytree(ROOT/'engine',repo/'engine',ignore=shutil.ignore_patterns('target','__pycache__'))
    shutil.copyfile(ROOT/'Cargo.lock',repo/'Cargo.lock')
    (repo/'Cargo.toml').write_text('[workspace]\nresolver="2"\nmembers=["engine/cell-runtime","engine/structural-key"]\n')
    crate=repo/'engine/cell-runtime';install(crate)
    session=HERE/'session.rs'
    if session.exists():shutil.copyfile(session,crate/'examples/single_witness_session.rs')
    env=dict(os.environ,CARGO_TARGET_DIR=str(a.out/'target'),CARGO_INCREMENTAL='0')
    cmd=['cargo','build','--offline','--release','-p','eggfuse-cell-runtime','--features','precomputed-forest,slot-transfer-audit','--bin','eggfuse-cell-runtime']
    if session.exists():cmd+=['--example','single_witness_session']
    subprocess.run(cmd,cwd=repo,env=env,check=True)
    for src,dest in [('eggfuse-cell-runtime','runtime')]+([('examples/single_witness_session','session')] if session.exists() else []):
        shutil.copy2(a.out/'target/release'/src,a.out/dest)
    (a.out/'build.json').write_text(json.dumps(dict(commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        binary=hashlib.sha256((a.out/'runtime').read_bytes()).hexdigest()),indent=1)+'\n')

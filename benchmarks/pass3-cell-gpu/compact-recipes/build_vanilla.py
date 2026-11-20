"""Build separate default-feature and audit binaries with one pinned Rust lockfile."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
def build(out):
    out.mkdir(parents=True,exist_ok=True)
    target=Path(os.environ['CARGO_TARGET_DIR'])
    meta={}
    for name,features in [('vanilla',[]),('vanilla-audit',['--features','audit'])]:
        subprocess.run(['cargo','build','--release','--offline','--locked','--manifest-path',HERE/'native/Cargo.toml',*features],check=True)
        dest=out/name
        shutil.copy2(target/'release/eggfuse-vanilla-benchmark',dest)
        meta[name]=hashlib.sha256(dest.read_bytes()).hexdigest()
    (out/'manifest.json').write_text(json.dumps(meta,indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('out',type=Path)
    build(parser.parse_args().out)

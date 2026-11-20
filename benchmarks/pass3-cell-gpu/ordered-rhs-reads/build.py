"""Use the complete frozen integrated runtime and its actual CLI allocator."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'joint-witness'))
import build as joint
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);a=p.parse_args()
    joint.build(a.out,True,True,True,cli_allocator=True,extensions=(
       'incremental-neural-index','baked-port-codes','adaptive-row-policy','witness-production-profile','multi-root-pages',
       'transaction-guards','single-signature-frontier','integrated-cpu-policy',HERE.name))

    path=a.out/'build.json'
    manifest=json.loads(path.read_text())
    manifest['sources'][HERE.name+'/projection.py']=hashlib.sha256((HERE/'projection.py').read_bytes()).hexdigest()
    path.write_text(json.dumps(manifest,indent=1)+'\n')

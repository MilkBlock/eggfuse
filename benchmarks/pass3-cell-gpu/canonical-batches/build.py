"""Compile one ordinary complete engine or a paired compact/ordinary build for the forward study."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'joint-witness'))
import build as joint

EXTENSIONS=(
    'incremental-neural-index','baked-port-codes','adaptive-row-policy','witness-production-profile',
    'multi-root-pages','transaction-guards','single-signature-frontier','integrated-cpu-policy',
    'learned-prefix-feasibility','projected-single-verifier','prepared-port-blocks','learned-atom-constraints',
    'tiered-port-projections','complete-generation',HERE.name,
)

def build_variant(out,compact,roots_only=False):
    os.environ["EGGFUSE_BENCH_CANON_ROOTS_ONLY"]="yes" if roots_only else "no"
    os.environ['EGGFUSE_BENCH_CANON_FORWARD']='compact' if compact else 'ordinary'
    joint.build(out,True,True,True,cli_allocator=True,extensions=EXTENSIONS)
    path=out/'build.json'
    manifest=json.loads(path.read_text());manifest['small_forward']=compact;manifest['roots_only']=roots_only
    for name in ('frames.py','forward.py'):
        manifest['sources'][HERE.name+'/'+name]=hashlib.sha256((HERE/name).read_bytes()).hexdigest()
    path.write_text(json.dumps(manifest,indent=1)+'\n')
    if not (out/'session').is_file():raise RuntimeError(f'build did not produce {out}/session')

def build_pair(out,compact,roots_only=False):
    build_variant(out,compact,roots_only)
    ordinary=out
    if compact:
        ordinary=out/'control'
        build_variant(ordinary,False)
    subprocess.run([sys.executable,HERE/'edges.py',ordinary]+([] if roots_only else ['--frame']),check=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('out',type=Path)
    m=p.add_mutually_exclusive_group();m.add_argument('--small-forward',action='store_true');m.add_argument('--roots-only',action='store_true')
    args=p.parse_args();build_pair(args.out,args.small_forward,args.roots_only)

"""Compare the three requested neural/verification placements on the same checked source prefix."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'coverage-certificate'))
from placement import study


def load_rust():
    manifest=HERE/'Cargo.toml'
    subprocess.run(['cargo','build','--release','--locked','--manifest-path',str(manifest)],check=True)
    metadata=json.loads(subprocess.check_output(['cargo','metadata','--no-deps','--format-version','1',
                                                '--manifest-path',str(manifest)]))
    lib=Path(metadata['target_directory'])/'release/libcell_proof_verifier.dylib'
    native=ctypes.CDLL(str(lib)).certify_cpu
    native.argtypes=[ctypes.c_void_p]*4
    native.restype=None
    return native


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('ref','weights','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product'])
    p.add_argument('--repeats',type=int,default=24)
    a=p.parse_args();a.arms=('cpu1/cpu','mps/cpu','mps/mps')
    report=study(a,load_rust())
    report['cpu_verifier']='Rust cell-proof-verifier';report['gpu_verifier']='Metal certify'
    a.out.write_text(json.dumps(report,indent=1)+'\n')

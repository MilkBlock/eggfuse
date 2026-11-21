"""Compile page-level verification into the same Run-wide staging profile."""
import argparse,importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('joint_build',HERE/'build.py');joint=importlib.util.module_from_spec(spec);spec.loader.exec_module(joint)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('out',type=Path);a=p.parse_args()
    joint.base.joint.build(a.out,True,True,True,cli_allocator=True,extensions=(*joint.base.EXTENSIONS,
        'speculative-cell-batches','run-proposal-waves','wave-cell-allocation','page-premise-programs','batched-cell-verifier'))

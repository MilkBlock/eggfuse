"""Build the original full joint CPU pipeline plus explicitly selected isolated ablations."""
import argparse
from pathlib import Path
import shutil
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'joint-witness'))
import build as joint


def build(out,baked):
    extensions=['incremental-neural-index']
    examples=[]
    if baked:
        extensions.append('baked-port-codes');examples.append('bake_port_codes')
    joint.build(out,True,True,True,cli_allocator=True,extensions=extensions,examples=examples)
    if baked:shutil.copy2(out/'target/release/examples/bake_port_codes',out/'bake')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);p.add_argument('--baked',action='store_true')
    a=p.parse_args();build(a.out,a.baked)

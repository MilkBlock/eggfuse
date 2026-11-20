"""Compile the code-table exporter and online CPU runtime together."""
import argparse
from pathlib import Path
import shutil
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'joint-witness'))
import build as joint


def build(out):
    joint.build(out,True,True,True,cli_allocator=True,extensions=('baked-port-codes',),examples=('bake_port_codes',))
    shutil.copy2(out/'target/release/examples/bake_port_codes',out/'bake')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('out',type=Path);build(p.parse_args().out)

"""Build same-address staged Cell publication into the group-authenticated wave engine."""
import argparse
import importlib.util
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("composed_build", HERE.parent/"composed-cpu/build.py")
base=importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out",type=Path)
    a=parser.parse_args()
    base.joint.build(a.out,True,True,True,cli_allocator=True,extensions=(
        *base.EXTENSIONS,"speculative-cell-batches","run-proposal-waves","wave-cell-allocation","group-named-cells","resident-cell-slabs",HERE.name))

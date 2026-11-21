"""Publish target-specific signed cross-Run and projected RHS libraries together."""
import argparse
from pathlib import Path
from runpy import run_path
import shutil

from library import atomic_write, catalog
HERE = Path(__file__).resolve().parent
bridge = run_path(str(HERE.parent/"explicit-parent-cell-composition/ripsat_bridge.py"))


def prepare(exp, prover, output):
    output.mkdir(parents=True, exist_ok=False)
    archive = output / "archive"
    shutil.copytree(HERE/"donor-evidence", archive)
    small = exp/"compact-holdouts-20261121-v1"
    donors = {n:small/(n+"-1703")/"program.json" for n in ("dot-product","jacobi-1d")}
    for name, base in (("sum-bits",small),("3mm",exp/"extra-pass3-transfer-v1")):
        target = base/(name+"-1703")/"program.json"
        checked = bridge["build"](archive/"evidence.json",donors,target,trust_index=archive/"trust.json")
        path = output/(name+".json")
        atomic_write(path,checked)
        bridge["load_checked"](path,target,trust_index=archive/"trust.json")
        library = catalog(donors.values(),target,prover.resolve(),5,4)
        atomic_write(output/(name+"-fragments.json"),library)
        print(name,len(library["entries"]),len(checked["strict_named"]["library"]),flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("exp","prover","output"):
        parser.add_argument(key,type=Path)
    args=parser.parse_args()
    prepare(args.exp,args.prover,args.output)

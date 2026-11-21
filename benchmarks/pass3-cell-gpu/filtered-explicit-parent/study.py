"""Run the native strict explicit-parent paired audit with identical scalar filtering at all depths."""
import argparse
import importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location("named_execution",HERE.parent/"explicit-parent-cell-composition/study.py")
strict=importlib.util.module_from_spec(sp);sp.loader.exec_module(strict)
original=strict.bake.settings

def filtered(req,rule):
    base=original(req,rule)
    return dict(base,rows=dict(base["rows"],scalar_certificates=True))

strict.bake.settings=filtered

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("exp","native","library","out"):
        p.add_argument(k,type=Path)
    p.add_argument("--cases",nargs="+",default=["sum-bits","3mm"])
    p.add_argument("--repeats",type=int,default=3)
    strict.run(p.parse_args())

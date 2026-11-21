"""Build the native full-Run issuer with a physical allocation decision after issuance."""
import argparse
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
base = run_path(str(HERE.parent / "composed-cpu/build.py"))
if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("out", type=Path)
    base["joint"].build(p.parse_args().out, True, True, True, cli_allocator=True,
                        extensions=(*base["EXTENSIONS"], "speculative-cell-batches", "run-proposal-waves",
                                    "wave-cell-allocation", "group-named-cells", "sealed-lane-claims", HERE.name))

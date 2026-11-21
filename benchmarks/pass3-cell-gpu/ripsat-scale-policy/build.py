"""Build the native CPU verifier and both comparison arms in one executable."""
import argparse
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
base = run_path(str(HERE.parent / "ripsat-set-receipt/build.py"))
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    base["prior"]["base"]["base"]["joint"].build(
        parser.parse_args().out, True, True, True, cli_allocator=True,
        extensions=(*base["EXTENSIONS"], "ripsat-issuance-rl", "ripsat-receipt-locality", "ripsat-block-verifier", HERE.name))

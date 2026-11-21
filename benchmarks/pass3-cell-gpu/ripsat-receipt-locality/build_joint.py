"""Build the receipt-read ablation on the same higher-order owner and queued requests."""
import argparse
from pathlib import Path
from runpy import run_path
HERE=Path(__file__).resolve().parent
base=run_path(str(HERE.parent/"ripsat-set-receipt/build.py"))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("out",type=Path)
    base["prior"]["base"]["base"]["joint"].build(p.parse_args().out,True,True,True,cli_allocator=True,
                       extensions=(*base["EXTENSIONS"],"ripsat-higher-cell",HERE.name))

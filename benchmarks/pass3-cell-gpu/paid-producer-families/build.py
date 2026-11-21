"""Add a learned producer-family right to the real integral mixed issuer."""
import argparse
from pathlib import Path
from runpy import run_path
HERE=Path(__file__).resolve().parent
joint=run_path(str(HERE.parent/'integral-filter-joint/build.py'))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('out',type=Path)
    joint['base']['joint'].build(p.parse_args().out,True,True,True,cli_allocator=True,extensions=(*joint['EXTENSIONS'],HERE.name))

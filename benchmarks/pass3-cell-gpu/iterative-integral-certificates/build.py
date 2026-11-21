"""Compile authenticated two-hop releases over the filtered mixed native issuer."""
import argparse
from pathlib import Path
from runpy import run_path
HERE=Path(__file__).resolve().parent
joint=run_path(str(HERE.parent/'integral-filter-joint/build.py'))
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('out',type=Path)
    joint['base']['joint'].build(parser.parse_args().out,True,True,True,cli_allocator=True,
                                extensions=(*joint['EXTENSIONS'],HERE.name))

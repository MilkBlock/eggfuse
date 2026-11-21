"""Build an optional higher-order owner around the authenticated native Set protocol."""
from argparse import ArgumentParser
from pathlib import Path
from runpy import run_path
HERE=Path(__file__).resolve().parent
direct=run_path(str(HERE.parent/'ripsat-set-receipt/build.py'))
if __name__=='__main__':
    p=ArgumentParser();p.add_argument('out',type=Path)
    direct['prior']['base']['base']['joint'].build(p.parse_args().out,True,True,True,cli_allocator=True,extensions=(*direct['EXTENSIONS'],HERE.name))

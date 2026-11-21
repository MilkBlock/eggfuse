"""Measure disjoint residual and signed strict unary sources with origin links."""
from pathlib import Path
from argparse import ArgumentParser
from runpy import run_path
HERE=Path(__file__).resolve().parent
base=run_path(str(HERE.parent/'filtered-explicit-parent/build.py'))
EXTENSIONS=(*base['extensions'],'filtered-explicit-parent',HERE.name)
if __name__=='__main__':
    p=ArgumentParser();p.add_argument('out',type=Path)
    base['base']['joint'].build(p.parse_args().out,True,True,True,cli_allocator=True,extensions=EXTENSIONS)

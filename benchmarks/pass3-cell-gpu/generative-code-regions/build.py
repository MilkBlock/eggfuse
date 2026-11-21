"""Append fixed learned-prefix regions to the measured compound and trained-single engine."""
import argparse
from pathlib import Path
from runpy import run_path
HERE=Path(__file__).resolve().parent
base=run_path(str(HERE.parent/'wide-fept-composition/build.py'))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path)
    base['base']['base']['joint'].build(p.parse_args().out,True,True,True,cli_allocator=True,
        extensions=(*base['EXTENSIONS'],'compound-family-ports',HERE.name))

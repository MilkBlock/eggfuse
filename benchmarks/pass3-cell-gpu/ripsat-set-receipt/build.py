"""Build the fresh constructor-Set publication port on the named partial Rust engine."""
from argparse import ArgumentParser
from pathlib import Path
from runpy import run_path
HERE=Path(__file__).resolve().parent
prior=run_path(str(HERE.parent/'strict-partial-named-ports/build.py'))
EXTENSIONS=(*prior['EXTENSIONS'],HERE.name)
if __name__=='__main__':
    parser=ArgumentParser(description=__doc__);parser.add_argument('out',type=Path)
    prior['base']['base']['joint'].build(parser.parse_args().out,True,True,True,cli_allocator=True,extensions=EXTENSIONS)

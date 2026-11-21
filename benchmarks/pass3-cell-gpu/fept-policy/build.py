from argparse import ArgumentParser
from pathlib import Path
from runpy import run_path
HERE=Path(__file__).resolve().parent
base=run_path(str(HERE.parent/'verified-wave-execution/build.py'))
if __name__=='__main__':
    p=ArgumentParser();p.add_argument("out",type=Path)
    base["base"]["joint"].build(p.parse_args().out,True,True,True,cli_allocator=True,
        extensions=(*base["extensions"],"token-constructor-births","causal-single-class",HERE.name))

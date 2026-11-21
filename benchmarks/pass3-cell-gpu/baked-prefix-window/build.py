from pathlib import Path
from argparse import ArgumentParser
from runpy import run_path
HERE=Path(__file__).resolve().parent
base=run_path(str(HERE.parent/'verified-wave-execution/build.py'))
if __name__=='__main__':
    parser=ArgumentParser();parser.add_argument('out',type=Path)
    base["base"]["joint"].build(parser.parse_args().out,True,True,True,cli_allocator=True,
        extensions=(*base["extensions"],"token-constructor-births","causal-single-class","generative-pair-buckets",HERE.name))

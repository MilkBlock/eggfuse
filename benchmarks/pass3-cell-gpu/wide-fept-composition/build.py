"""Build the trained singleton class and wide typed pair family and the native RSS observer in one binary."""
from argparse import ArgumentParser
from pathlib import Path
from runpy import run_path
HERE=Path(__file__).resolve().parent
base=run_path(str(HERE.parent/'verified-wave-execution/build.py'))
EXTENSIONS=(*base['extensions'],'token-constructor-births','causal-single-class','fept-policy',
            'generative-pair-buckets','generative-pair-families','verified-wave-rss',HERE.name)
if __name__=='__main__':
    p=ArgumentParser();p.add_argument('out',type=Path)
    base['base']['joint'].build(p.parse_args().out,True,True,True,cli_allocator=True,extensions=EXTENSIONS)

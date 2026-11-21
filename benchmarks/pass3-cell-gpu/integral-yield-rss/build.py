"""Append independent inference-window observation to the joint issuer; reuse the identical native CPU."""
import argparse
from hashlib import sha256
from pathlib import Path
from runpy import run_path
from shutil import copy2
import json
HERE=Path(__file__).resolve().parent
upstream=run_path(str(HERE.parent/'integral-filter-joint/build.py'))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('out',type=Path);p.add_argument('vanilla',type=Path)
    a=p.parse_args()
    expected=json.loads((HERE.parent/'verified-wave-rss/manifest.json').read_bytes())['build_sha256']['vanilla']
    if sha256(a.vanilla.read_bytes()).hexdigest()!=expected:raise ValueError('unmatched default-feature memory probe')
    upstream['base']['joint'].build(a.out,True,True,True,cli_allocator=True,extensions=(*upstream['EXTENSIONS'],HERE.name))
    copy2(a.vanilla,a.out/'vanilla')

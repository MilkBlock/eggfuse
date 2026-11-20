"""Compile additional eggcc Pass 3 workloads without reading executions or refitting weights."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent;GPU=HERE.parent
CASES=('3mm','deriche')
def hashfile(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def prepare(out):
    out.mkdir(parents=True,exist_ok=False);manifest={}
    suite=HERE.parents[2]/'workloads/pass3'
    for case in CASES:
        src=next(c for c in json.loads((suite/'suite.json').read_bytes())['cases'] if c['name']==case)
        assert src['pass_number']==3
        program=out/case;image=out/(case+'-image');bundle=out/(case+'-1703')
        subprocess.run(['cargo','cell-compile','--case',case,'--output',program],check=True)
        subprocess.run([sys.executable,GPU/'codec.py',program/'program.json',image],check=True)
        subprocess.run([sys.executable,GPU/'joint-witness/prepare.py',program/'program.json',image,bundle,
                        '--seed','1703','--policy','certified'],check=True)
        manifest[case]=dict(source=src['sha256'],program=hashfile(program/'program.json'),seed=1703,
                            parts={s:hashfile(suite/s) for s in src['parts']},plans=hashfile(bundle/'plans.json'))
        (out/'manifest.json').write_text(json.dumps(manifest,indent=1)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('out',type=Path);prepare(p.parse_args().out)

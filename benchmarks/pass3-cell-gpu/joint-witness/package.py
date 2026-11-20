"""Archive small reproducible evidence; large native ordinal streams stay as hashed experiment artifacts."""
import argparse
import hashlib
import json
from pathlib import Path


def read(p):return json.loads(p.read_bytes())


def package(experiments,dest):
    runs={
        'selective':'joint-98-named-assisted-v4',
        'no_residual':'joint-98-named-certified-v4',
        'balanced':'joint-98-balanced-v1',
        'development':'joint-98-dev-autonomous-v1',
        'negative':'joint-98-checked-v4',
        'state_mask':'joint-98-template-audit-v1',
        'timing':'joint-98-primary-timings-v1',
    }
    manifest={}
    for key,trial in runs.items():
        folder=experiments/trial
        result=read(folder/'results.json')
        if key=='negative':
            for k,v in result.items():
                # The original zero-state ledger used a different attribution convention.
                # Use the separately archived corrected intervention in state_mask.
                v.pop('zero-state',None)
        if key=='state_mask':result={k:v['zero-state'] for k,v in result.items()}
        (dest/f'{key}.json').write_text(json.dumps(result,indent=1)+'\n')
        manifest[key]=dict(directory=trial,results_file_sha256=hashlib.sha256((folder/'results.json').read_bytes()).hexdigest(),
                           ordinals={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.glob('*-ordinals.json.gz'))})
    (dest/'manifest.json').write_text(json.dumps(manifest,indent=1)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('experiments',type=Path);p.add_argument('dest',type=Path)
    a=p.parse_args();a.dest.mkdir(exist_ok=True,parents=True);package(a.experiments,a.dest)

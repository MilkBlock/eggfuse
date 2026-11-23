"""Alternate the original and projected port encoders on identical full live assist workloads."""
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import torch
from live_domain_study import measure


def compare(root,case,binary,weights,seed):
    pairs=[]
    with TemporaryDirectory() as directory:
        tmp=Path(directory)
        for i in range(4):
            pair=[]
            for projected in ((False,True) if i%2==0 else (True,False)):
                measure(root/case,binary,weights,seed,projected,tmp/'result.json',tmp/'stream.json')
                report=json.loads((tmp/'result.json').read_bytes())
                pair.append(report)
            raw=next(r for r in pair if not r['projected'])
            reduced=next(r for r in pair if r['projected'])
            if raw['stream']!=reduced['stream'] or raw['result']['counts']!=reduced['result']['counts']:
                raise ValueError('projection changed the named stream')
            pairs.append(pair)
    return pairs


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('root','binary','weights','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',required=True)
    a=p.parse_args()
    torch.set_num_threads(1)
    seeds={r['directory']:r['seed'] for r in json.loads((a.root/'manifest.json').read_bytes())}
    for n in a.cases:
        pairs=compare(a.root,n,a.binary,a.weights,1703+seeds.get(n,0))
        (a.out/(n+'-pairs.json')).write_text(json.dumps(pairs,indent=2)+'\n')
        print(n,[round(p[0]['wall'],2) for p in pairs],flush=True)

"""Enumerate all distinct observable input vectors for this finite conditional Cell library."""
import argparse
import json
from pathlib import Path
import numpy as np
from synthetic import INTERFACES, ports


def certificates(path,threshold):
    if threshold != 1:raise ValueError('this domain proof requires the compiled equality guard at one')
    # Clipping maps every signed integer to one of 65 representatives; equality/greater
    # are unchanged outside [-32,32]. Any positive depth above 16 maps to depth 16.
    x=np.array([ports(rule,op,n,d) for rule,op in INTERFACES for n in range(-32,33)
                for d in range(1,17)],dtype=np.float32)
    report={}
    for k,v in json.loads(path.read_bytes())['policies'].items():
        g=v['gate'];z=np.full(len(x),g['bias'],dtype=np.float32)
        for col,w in enumerate(g['weights']):z+=x[:,col]*np.float32(w)
        selected=int((z>=np.float32(g['threshold'])).sum())
        report[k]=dict(vectors=len(z),selected=selected,max=float(z.max()),min=float(z.min()),
                       max_margin=float(np.abs(z).max()),min_margin=float(np.abs(z).min()),
                       constant='off' if selected==0 else 'on' if selected==len(z) else None)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('weights',type=Path);p.add_argument('out',type=Path);a=p.parse_args()
    b=Path(__file__).resolve().parents[1]/'higher-order-bake';f=json.loads((b/'catalog.json').read_bytes())['family']
    assert {tuple(v) for v in json.loads((b/'growth.json').read_bytes())['second_round']}==set(INTERFACES)
    a.out.write_text(json.dumps(certificates(a.weights,f['threshold']),indent=1)+'\n')

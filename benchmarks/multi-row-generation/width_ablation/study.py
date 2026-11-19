"""CPU-only input panels for zero-update row expansion."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'eclass_ablation'
sys.path.append(str(BASE))
from data.source import base_group, dataset

SEEDS=(1703,1709)
INPUTS=('a','b','requests','a_port','request_ports','phase','committed','external','external_ports')

def templates():
    return json.loads((BASE/'corpus/manifest.json').read_text())['templates']


def fresh_panel(t):
    records=[example for g in range(720,752) for example in base_group(t,'test',g)]
    panel={k:np.stack([ex[k] for ex in records]) for k in records[0]}
    panel.update(template=t,template_id=t['id'],split='test',fresh=True)
    return panel


def array_digest(d):
    h=hashlib.sha256()
    for k in INPUTS+('target1','target2','request_legal'):h.update(d[k].tobytes())
    return h.hexdigest()


def input_keys(d):
    return {hashlib.sha256(b''.join(np.ascontiguousarray(d[k][i]).tobytes() for k in INPUTS)).digest()
            for i in range(len(d['a']))}


def freeze():
    ts=templates();seen=set()
    for t in ts:
        if t['split']=='train':seen.update(input_keys(dataset('train',t)))
        seen.update(input_keys(dataset('test',t)))
    results={}
    for t in ts:
        if t['split']=='heldout':
            panel=fresh_panel(t);keys=input_keys(panel);overlap=len(keys&seen)
            if overlap:raise ValueError(f"fresh-panel input overlap {t['id']}: {overlap}")
            results[t['id']]=dict(graphs=len(panel['a']),nonempty=int((panel['target2'][...,0].sum(1)>0).sum()),
                                  obligations=int(panel['target2'][...,0].sum()),digest=array_digest(panel),existing_overlap=overlap)
    return results
if __name__=='__main__':print(json.dumps(freeze(),indent=2))

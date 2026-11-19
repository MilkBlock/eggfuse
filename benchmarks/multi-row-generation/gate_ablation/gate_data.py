"""Frozen counterfactual source panels for evaluating per-round gates."""
from hashlib import sha256
import json
from pathlib import Path
import sys

import numpy as np

BASE = Path(__file__).resolve().parents[1]
sys.path.append(str(BASE))
from eclass_ablation.data import dataset
from eclass_ablation.data.source import base_group
from eclass_ablation.data.runtime import CORPUS

FIRST_GROUP, STOP_GROUP = 2160, 2192
SEEDS = (1703,1709)
INPUTS = ('a','b','requests','a_port','request_ports','phase','committed','external','external_ports')
RAW = ('a','b','requests','phase','committed','external')


def templates():
    return json.loads((CORPUS/'manifest.json').read_text())['templates']


def _panel(template, begin, stop):
    records = [record for group in range(begin,stop) for record in base_group(template,'test',group)]
    d = {k:np.stack([record[k] for record in records]) for k in records[0]}
    d.update(template=template, template_id=template['id'], split='test',fresh=True)
    return d


def fresh_panel(template):
    return _panel(template,FIRST_GROUP,STOP_GROUP)


def array_digest(d):
    h=sha256()
    for k in INPUTS+('target1','target2','request_legal'):
        h.update(np.ascontiguousarray(d[k]).tobytes())
    return h.hexdigest()


def _keys(panel, fields):
    return {sha256(b''.join(np.ascontiguousarray(panel[k][i]).tobytes() for k in fields)).digest()
            for i in range(len(panel['a']))}


def _base_keys(panel):
    # The producer tables only, to catch a repeated base group even if the four
    # source states, request tags or controlled origin intervention were changed.
    return _keys(panel,('a','b'))


def freeze():
    ts=templates();world={scope:{'encoded':set(),'raw':set(),'base':set()} for scope in ('train','fig20_test','fig04_test','fig05_test')}
    def register(name,panel):
        world[name]['encoded'].update(_keys(panel,INPUTS));world[name]['raw'].update(_keys(panel,RAW));world[name]['base'].update(_base_keys(panel))
    for t in ts:
        if t['split']=='train':register('train',dataset('train',t))
        else:
            register('fig04_test',_panel(t,720,752));register('fig05_test',_panel(t,1440,1472))
        register('fig20_test',dataset('test',t))
    held=[t for t in ts if t['split']=='heldout']
    if len(held)!=3:raise ValueError('expected the original three held-out templates')
    if {t['family_id'] for t in held}&{t['family_id'] for t in ts if t['split']=='train'}:
        raise ValueError('template-family leakage')
    reports={}
    for t in held:
        d=fresh_panel(t);indices,counts=np.unique(d['group_id'],return_counts=True)
        np.testing.assert_array_equal(indices,np.arange(FIRST_GROUP,STOP_GROUP));np.testing.assert_array_equal(counts,np.full(len(indices),8))
        current={'encoded':_keys(d,INPUTS),'raw':_keys(d,RAW),'base':_base_keys(d)}
        overlap={name:{k:len(v & prior[k]) for k,v in current.items()} for name,prior in world.items()}
        if any(count for v in overlap.values() for count in v.values()):raise ValueError(f"{t['id']}: old source overlap {overlap}")
        one,two=d['target1'][...,0].sum(1),d['target2'][...,0].sum(1)
        if not (two>0).all():raise ValueError('gate source panel must be nonempty')
        reports[t['id']]=dict(graphs=len(two),digest=array_digest(d),source_group_count=len(indices),
            blind_graphs=int(d['blind'].sum()),old_overlap=overlap,unique={k:len(v) for k,v in current.items()},
            source_obligations=dict(run1=int(one.sum()),run2=int(two.sum())),
            run2_obligation_histogram={str(k):int(n) for k,n in zip(*np.unique(two,return_counts=True))},
            nonempty_run2=int((two>0).sum()),family=t['family_id'])
    return dict(schema='eggfuse.row-gates.panels/v1',group_range=[FIRST_GROUP,STOP_GROUP-1],
        overlap_scopes={name:{k:len(v) for k,v in bucket.items()} for name,bucket in world.items()},panels=reports,
        source_sha256={name:sha256((CORPUS/name).read_bytes()).hexdigest() for name in ('manifest.json','replay-evidence.json','extra-events.json')})


def save_or_check(record,path):
    path=Path(path)
    if path.exists():
        if json.loads(path.read_text())!=record:raise ValueError(f'input freeze changed at {path}')
    else:
        tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(record,indent=2)+'\n');tmp.replace(path)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);args=p.parse_args()
    frozen=freeze();save_or_check(frozen,args.output)
    print(json.dumps({k:(v['graphs'],v['blind_graphs'],v['run2_obligation_histogram']) for k,v in frozen['panels'].items()},indent=2))

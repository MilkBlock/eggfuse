"""Replay the saved inference outcomes with NumPy, after all GPU work has finished."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'data'))
from crossrun_data import dataset
from crossrun_audit import audit, audit_twins


def check_pair_tokens(tokens, first):
    fields = (first['active'], *first['pointers'].transpose(2,0,1), *first['fields'].transpose(2,0,1))
    offset = 64
    if tokens.shape[-1] != 90 or not np.isfinite(tokens).all():
        raise ValueError('invalid Pair token')
    for width, value in zip((2,4,4,8,4,4),fields):
        np.testing.assert_array_equal(tokens[...,offset:offset+width],np.eye(width)[value])
        offset += width


def main():
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);args=parser.parse_args()
    report=json.loads((args.root/'result.json').read_text());panels={name:dataset(name) for name in ('iid','left_collision','right_collision')}
    checked=0
    for label,ref in report['panels'].items():
        arm,seed,split,mask=label.split('-');data=panels[split]
        with np.load(args.root/'traces'/f'{label}.npz',allow_pickle=False) as z:
            first={k:z['one_'+k] for k in ('active','pointers','fields')};second={k:z['two_'+k] for k in first}
            check_pair_tokens(z['token'],first)
        metrics=audit(data['a'],data['b'],data['requests'],first,second)
        for stage in ('run1','run2'):
            assert ref[stage]=={k:v for k,v in metrics[stage].items() if k!='per_graph'},(label,stage)
        assert [g['complete'] for g in metrics['run2']['per_graph']]==report['complete_by_graph'][label]
        assert ref['both_complete_graphs']==metrics['both_complete_graphs']
        if split.endswith('collision'):
            assert ref['twins']==audit_twins(data['a'],data['b'],data['requests'],first,second)
        checked+=1
    assert checked==54 and 'mlx.core' not in sys.modules
    print(json.dumps(dict(checked=checked,graphs_per_panel=256,stages=2,posthoc_cpu_replay='pass')))

if __name__=='__main__':main()

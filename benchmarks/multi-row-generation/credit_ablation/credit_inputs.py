"""Frozen, CPU-only formal panels for the held-out credit assignment study."""
from pathlib import Path
import hashlib
import json
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
WIDTH = HERE.parent / 'width_ablation'
FIG20 = HERE.parent / 'eclass_ablation'
sys.path[:0] = [str(WIDTH), str(FIG20)]
from study import templates, dataset, array_digest, input_keys, fresh_panel as width_panel
from data.source import base_group

SEEDS = (1703, 1709)
ARMS = ('zero', 'supervised', 'team', 'counterfactual')
FIRST_GROUP, STOP_GROUP = 1440, 1472


def fresh_panel(template):
    rows = [record for group in range(FIRST_GROUP, STOP_GROUP)
            for record in base_group(template, 'test', group)]
    panel = {key: np.stack([record[key] for record in rows]) for key in rows[0]}
    panel.update(template=template, template_id=template['id'], split='test', fresh=True)
    return panel


def freeze():
    old = {'training': set(), 'fig20_test': set(), 'fig04_test': set()}
    ts = templates()
    for t in ts:
        if t['split'] == 'train':
            old['training'].update(input_keys(dataset('train',t)))
        else:
            old['fig04_test'].update(input_keys(width_panel(t)))
        old['fig20_test'].update(input_keys(dataset('test',t)))
    held = [t for t in ts if t['split']=='heldout']
    if len(held)!=3:
        raise ValueError('expected the original three held-out rules')
    result = {}
    for t in held:
        d = fresh_panel(t)
        keys = input_keys(d)
        overlap = {name:len(keys & prior) for name,prior in old.items()}
        if any(overlap.values()):
            raise ValueError(f"overlap for {t['id']}: {overlap}")
        # Source states and variants form one paired 8-graph experiment.
        by_group = np.unique(d['group_id'], return_counts=True)
        np.testing.assert_array_equal(by_group[0], np.arange(FIRST_GROUP, STOP_GROUP))
        np.testing.assert_array_equal(by_group[1], 8*np.ones(STOP_GROUP-FIRST_GROUP,dtype=int))
        result[t['id']] = dict(digest=array_digest(d), graphs=len(d['a']),
                              strata={'blind':int(d['blind'].sum()),'targeted':int((1-d['blind']).sum())},
                              nonempty=int((d['target2'][...,0].sum(1)>0).sum()),
                              obligations=int(d['target2'][...,0].sum()), existing_input_overlaps=overlap,
                              frozen_unique_inputs=len(keys))
    return dict(group_range=[FIRST_GROUP,STOP_GROUP-1],panels=result,
                reference_unique_inputs={name:len(keys) for name,keys in old.items()},
                heldout_source_sha256=hashlib.sha256((FIG20/'corpus/manifest.json').read_bytes()).hexdigest())


def save_or_check(record, path):
    if path.exists():
        if json.loads(path.read_text()) != record:
            raise ValueError(f'frozen input digest mismatch: {path}')
    else:
        tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(record,indent=2)+'\n');tmp.replace(path)

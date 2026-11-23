"""Condense paired rule-frontier and end-to-end measurements from immutable reports."""
import argparse
from pathlib import Path
import json

from mixed_results import exclusive, read


def summarize(folder):
    training = read(folder/'training.json')
    result = dict(training=training, arms={})
    for arm in ('mask','uniform','stratified'):
        native = read(folder/f'{arm}-native.json')
        census = read(folder/f'{arm}-census.json')
        held = read(folder/f'{arm}-held.json')
        if native['weights_sha256'] != census['weights_sha256'] or native['verifier_sha256'] != held['build_sha256']:
            raise ValueError('unpaired receiver or rule weights')
        splits = {}
        for name, s in held['splits'].items():
            cases = s['exclusive']['cases']
            splits[name] = dict(shadow=s['shadow'],exclusive=exclusive(cases))
            for c in cases:
                if name=='held_eggcc' and exclusive([c])['counts'] != native['cases'][c['case']]['exclusive']['counts']:
                    raise ValueError('standalone exclusive replay differs')
        result['arms'][arm] = dict(native=native,shadow_rule_census=census,splits=splits)
    result['stratified_four_waves'] = read(folder/'stratified-waves.json')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',type=Path)
    p.add_argument('output',type=Path)
    a=p.parse_args()
    a.output.write_text(json.dumps(summarize(a.directory),indent=2)+'\n')

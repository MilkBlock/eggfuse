"""Summarize the frozen-backbone ablation and retain comparable denominators."""
import argparse
import hashlib
import json
from pathlib import Path

from mixed_results import exclusive, read


def summarize(folder, previous):
    prior = read(previous)
    reference = prior['holdouts']['after']
    result = dict(training=read(folder/'training.json'), arms={})
    native = read(folder/'sum-divisors-reference.json')
    replay = read(folder/'sum-divisors-replay.json')
    if any(native[k] != replay[k] for k in ('state_sha','schedule','rhs','writes','resumes','events')):
        raise ValueError('additional native holdout failed M0')
    if (replay['unused'] or replay['counts']['accepted'] != native['matches']
            or replay['counts']['duplicates'] or replay['counts']['rejected']):
        raise ValueError('additional holdout reference ledger incomplete')
    for mode in ('global', 'typed'):
        held = read(folder/f'{mode}-held.json')
        audit = read(folder/f'{mode}-rule.json')
        census = read(folder/f'{mode}-census.json')
        weight_hash = hashlib.sha256((folder/f'{mode}.pt').read_bytes()).hexdigest()
        if audit['weights_sha256'] != weight_hash or census['weights_sha256'] != weight_hash:
            raise ValueError('different rule checkpoints')
        if held['build_sha256'] != prior['verifier_sha256'] or not held['field_pointer']:
            raise ValueError('different receiver or parent head')
        if set(held['splits']) != set(reference['splits']):
            raise ValueError('different evaluation splits')
        splits = {}
        for name, group in held['splits'].items():
            cases = group['exclusive']['cases']
            totals = exclusive(cases)
            ref = reference['splits'][name]['exclusive']['counts']
            for key in ('programs','reference_commits','reference_runs'):
                if totals['counts'][key] != ref[key]:
                    raise ValueError(f'different {name} exposure')
            splits[name] = dict(shadow=group['shadow'], exclusive=totals)
            if name == 'held_eggcc':
                splits[name]['exclusive_by_program'] = {c['case']:exclusive([c]) for c in cases}
        for name, observations in audit['cases'].items():
            for group in ('with_commits','without_commits'):
                if observations[group]['sample'] != prior['rule_head']['after']['cases'][name][group]['sample']:
                    raise ValueError('different source Run sample')
        online = read(folder/f'sum-divisors-{mode}.json')
        prefix = 0
        for i, (a,b) in enumerate(zip(native['rhs'],online['rhs_by_run'])):
            if a != b or native['writes'][i] != online['writes_by_run'][i] or native['schedule'][i] != online['source_schedule'][i]:
                break
            prefix += native['schedule'][i][4]
        online.update(case='sum-divisors', reference_commits=native['matches'], reference_runs=native['runs'],
                      reference_seconds=native['seconds'], reference_state_equal=online['state_sha']==native['state_sha'],
                      certified_reference_prefix_commits=prefix)
        result['arms'][mode] = dict(additional_holdout=exclusive([online]), weights_sha256=weight_hash, verifier_sha256=held['build_sha256'],
                                    census=census['cases'], sampled_rule_audit=audit['cases'], splits=splits)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('folder','previous','output'):
        p.add_argument(name,type=Path)
    a = p.parse_args()
    a.output.write_text(json.dumps(summarize(a.folder,a.previous),indent=2)+'\n')

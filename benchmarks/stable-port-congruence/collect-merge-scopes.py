#!/usr/bin/env python3
"""Collect checked merge effects, output influence, and actual progress costs."""
import argparse
import json
from pathlib import Path
import re


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def collect(root, output):
    validation = {}
    for suffix in ('workspace-tests', 'tests', 'non-sparse-tests'):
        log = (root / f'merge-scopes-{suffix}.log').read_text()
        assert 'test result: FAILED' not in log
        counts = [tuple(map(int, row)) for row in re.findall(
            r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', log)]
        assert counts and sum(row[1] for row in counts) == 0
        validation[suffix] = dict(zip(('passed', 'failed', 'ignored'), map(sum, zip(*counts))))
    log = (root / 'merge-scopes-minimal-check.log').read_text()
    assert 'Finished' in log and 'error:' not in log
    validation['no_default_features'] = 'compile check passed'
    write(output / 'merge-scopes-validation.json', validation)

    fixture = read(root / 'merge-scopes-fixture.json')
    point = fixture['checkpoint']
    assert not point['executor']['global_observer']
    assert point['graph']['pending_tasks'] > 0
    assert point['smaller_facts'] == point['seen_c_facts'] == 1
    assert point['executor']['stats']['executed_bindings_while_pending'] == 1
    assert point['graph']['stats']['opaque_full_completions'] == 0
    assert fixture['exact_final_state_and_ordered_bindings']
    assert fixture['final_executor']['pending_anchors'] == 0
    assert fixture['final_executor']['retained_contexts'] == 0
    write(output / 'merge-scopes-fixture.json', fixture)

    audit = read(root / 'merge-scopes-final-audit/results.json')
    old, new = (audit['cases']['sum-bits']['lanes'][k] for k in ('local_congruence', 'merge_scopes'))
    previous = read(output / 'port-scopes-audit.json')
    assert old['hashes'] == new['hashes'] == previous['hashes']
    assert old['stats'] == new['stats']
    assert new['runs'] == 1428 and not new['scoped_executor']['global_observer']
    assert not new['scoped_completion']['plan']['opaque_tables']
    assert new['scoped_completion']['stats']['opaque_full_completions'] == 0
    assert new['port_completion']['stats']['peak_group_visits'] <= new['port_completion']['visit_budget_per_group']
    trials = {}
    for name, directory in (
        ('input_union_influence', 'merge-scopes-audit'),
        ('birth_as_result_union', 'merge-scopes-output-audit'),
    ):
        path = root / directory / 'results.json'
        if path.exists():
            trial = read(path)
            lane = trial['cases']['sum-bits']['lanes']['merge_scopes']
            trials[name] = {key: lane[key] for key in ('hashes', 'port_completion', 'scoped_completion', 'scoped_executor')}
            trials[name]['runtime_sha256'] = trial['runtime_sha256']
        else:
            trials[name] = read(output / 'merge-scopes-audit.json')['rejected_overapproximation'][name]
        assert trials[name]['hashes'] == new['hashes']
    changes = {}
    for category in ('port_completion', 'scoped_completion', 'scoped_executor'):
        before, after = previous[category]['stats'], new[category]['stats']
        changes[category] = {
            key: {'before': before.get(key, 0), 'after': value, 'delta': value - before.get(key, 0)}
            for key, value in after.items()
            if isinstance(value, int) and value != before.get(key, 0)
        }
    write(output / 'merge-scopes-audit.json', {
        'scope': 'standalone Cell CPU, actual single-thread Executor; no timing or parallel claim',
        'baseline_revision': 'f8238efd',
        'runtime_sha256': audit['runtime_sha256'],
        'program_file_sha256': new['program_file_sha256'],
        'hashes': new['hashes'], 'runs': new['runs'],
        'exact_ordered_semantics_match': True,
        'ordinary_runtime_counts_match_global_control': True,
        'admitted_as_performance_improvement': False,
        'port_completion': new['port_completion'],
        'scoped_executor': new['scoped_executor'],
        'scoped_completion': new['scoped_completion'],
        'counter_changes_from_previous_experiment': changes,
        'rejected_overapproximation': trials,
        'read_selection_validation': 'The integration fixture alone also passed with read selection removed because constructor births independently selected that chain. A separate three-table selection unit test isolates the read-only dependency; no semantic corruption is claimed from the exploratory negative control.',
        'remaining': 'bound source accesses/writes, same-table regions, cheaper scope proof, ownership of concurrent publication and unions, real workers and complete-cost admission',
    })


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    collect(args.root, args.output)

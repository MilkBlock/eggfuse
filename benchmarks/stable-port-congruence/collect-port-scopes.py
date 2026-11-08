#!/usr/bin/env python3
"""Preserve concrete-port progress evidence and the rejected workload overhead."""
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
        name = f'port-scopes-{suffix}'
        log = (root / f'{name}.log').read_text()
        assert 'test result: FAILED' not in log
        counts = [tuple(map(int, row)) for row in re.findall(
            r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', log)]
        assert counts and sum(row[1] for row in counts) == 0
        validation[name] = dict(zip(('passed', 'failed', 'ignored'), map(sum, zip(*counts))))
    log = (root / 'port-scopes-minimal-check.log').read_text()
    assert 'Finished' in log and 'error:' not in log
    validation['no_default_features'] = 'compile check passed'
    write(output / 'port-scopes-validation.json', validation)

    fixture = read(root / 'port-scopes-fixture.json')
    point = fixture['checkpoint']
    assert not point['executor']['global_observer']
    assert not point['executor']['compiler_admits_deferral']
    assert point['graph']['pending_tasks'] > 0 and point['executor']['pending_anchors'] > 0
    assert point['seen_b_facts'] == 1
    assert point['executor']['stats']['executed_bindings_while_pending'] == 2
    assert fixture['exact_final_state_and_ordered_bindings']
    assert fixture['final_executor']['pending_anchors'] == 0
    assert fixture['final_executor']['retained_contexts'] == 0
    write(output / 'port-scopes-fixture.json', fixture)

    audit = read(root / 'port-scopes-audit/results.json')
    old, new = (audit['cases']['sum-bits']['lanes'][k] for k in ('scoped_executor', 'port_scopes'))
    previous = read(output / 'scoped-executor-audit.json')
    assert old['hashes'] == new['hashes'] == previous['hashes']
    assert new['runs'] == 1428
    for key in ('stats', 'stable_ports', 'publication'):
        assert old[key] == new[key], key
    assert not new['scoped_executor']['global_observer']
    assert new['scoped_executor']['stats']['executed_bindings_while_pending'] == 0
    assert new['scoped_executor']['stats']['runs_with_unrelated_pending'] == 0
    counts = new['port_completion']['stats']
    assert counts['peak_group_visits'] <= new['port_completion']['visit_budget_per_group']
    pilot = root / 'port-scopes-first-audit/results.json'
    if pilot.exists():
        trial = read(pilot)
        lane = trial['cases']['sum-bits']['lanes']['port_scopes']
        rejected = {
            'runtime_sha256': trial['runtime_sha256'],
            'hashes': lane['hashes'],
            'port_completion': lane['port_completion'],
            'scoped_executor': lane['scoped_executor'],
            'reason': 'repeated concrete influence discovery and global typed boundaries; no useful binding while pending; also predates incoming-union write gate',
        }
    else:
        # Historical code is not required to reproduce the accepted experiment.
        rejected = read(output / 'port-scopes-audit.json')['rejected_first_probe']
    assert rejected['hashes'] == new['hashes']
    assert counts['membership_checks'] < rejected['port_completion']['stats']['membership_checks']
    program = read(root / 'sum-program.json')
    tables = program['source_core']['tables']
    named_boundaries = {}
    for category in ('global_boundaries_by_table', 'pending_global_by_table'):
        named_boundaries[category] = [
            {'table': int(t), 'name': tables[int(t)]['name'], 'occurrences': count,
             'merge': tables[int(t)]['merge'], 'schema': tables[int(t)]['schema']}
            for t, count in counts[category].items()
        ]
    write(output / 'port-scopes-audit.json', {
        'scope': 'standalone Cell CPU, actual single-thread Executor; no timing or parallel claim',
        'baseline_revision': 'e0c61d3a',
        'runtime_sha256': audit['runtime_sha256'],
        'program_file_sha256': new['program_file_sha256'],
        'hashes': new['hashes'], 'runs': new['runs'],
        'exact_ordered_semantics_match': True,
        'ordinary_stats_stable_ports_and_publication_counts_match': True,
        'same_sort_independence': 'verified in fixture, including shared unmodified input and unrelated mutable table',
        'same_table_independence_verified': False,
        'useful_main_workload_progress_while_pending': False,
        'admitted_as_performance_improvement': False,
        'port_completion': new['port_completion'],
        'scoped_executor': new['scoped_executor'],
        'scoped_completion': new['scoped_completion'],
        'named_global_boundaries': named_boundaries,
        'rejected_first_probe': rejected,
        'negative_control': 'Removing incoming-union write demand fails the no-dependent-source-bypass assertion; final graph alone still matches in that fixture. This is not evidence of observed semantic corruption.',
        'remaining': 'precise merge/container effects and bound incoming writes, same-table scopes, ownership of parallel publication and unions, workers and complete-cost admission',
    })


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    collect(args.root, args.output)

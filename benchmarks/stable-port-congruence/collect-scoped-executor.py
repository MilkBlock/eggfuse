#!/usr/bin/env python3
"""Retain actual Executor progress, replacement costs and the main-workload limit."""
import argparse
import json
from pathlib import Path
import re


def collect(root, output):
    validation = {}
    for suffix in ('workspace-tests', 'tests', 'non-sparse-tests'):
        name = f'scoped-executor-{suffix}'
        log = (root / f'{name}.log').read_text()
        assert 'test result: FAILED' not in log
        counts = [tuple(map(int, row)) for row in re.findall(
            r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', log)]
        assert counts and sum(row[1] for row in counts) == 0
        validation[name] = dict(zip(('passed', 'failed', 'ignored'), map(sum, zip(*counts))))
    log = (root / 'scoped-executor-minimal-check.log').read_text()
    assert 'Finished' in log and 'error:' not in log
    validation['no_default_features'] = 'compile check passed'
    (output / 'scoped-executor-validation.json').write_text(json.dumps(validation, indent=2) + '\n')

    fixture = json.loads((root / 'scoped-executor-fixture.json').read_text())
    checkpoint = fixture['after_b_consumption']
    assert not checkpoint['executor']['global_observer']
    assert checkpoint['graph']['pending_tasks'] > 0
    assert checkpoint['executor']['pending_anchors'] > 0
    assert checkpoint['seen_b_facts'] == 1 and checkpoint['third_run_changed']
    assert checkpoint['third_run_bindings'] == 1
    assert fixture['final_graph']['pending_tasks'] == 0
    assert fixture['final_executor']['retained_contexts'] == 0
    assert fixture['final_state_and_ordered_step_bindings_match']
    for key in ('reference_spine', 'scoped_spine'):
        fixture[key] = {k:v for k,v in fixture[key].items() if not k.endswith('_seconds')}
    (output / 'scoped-executor-fixture.json').write_text(json.dumps(fixture, indent=2) + '\n')

    audit = json.loads((root / 'scoped-executor-audit/results.json').read_text())
    old, new = (audit['cases']['sum-bits']['lanes'][k] for k in ('scoped_queues', 'scoped_executor'))
    assert old['hashes'] == new['hashes']
    # Check the control against the previously accepted binary's evidence too.
    previous = json.loads((output / 'scoped-core-audit.json').read_text())
    assert old['hashes'] == previous['hashes']
    for key in ('stats', 'stable_ports', 'publication', 'scoped_completion'):
        assert old[key] == new[key], key
    assert not new['scoped_executor']['global_observer']
    assert not new['scoped_executor']['compiler_admits_deferral']
    assert new['scoped_executor']['stats']['partial_publications'] == 0
    assert new['scoped_executor']['stats']['ruleset_waits'] == 0
    trial_path = root / 'scoped-executor-unspecialized-audit/results.json'
    if trial_path.exists():
        trial_audit = json.loads(trial_path.read_text())
        trial = trial_audit['cases']['sum-bits']['lanes']['scoped_executor']
        rejected = {
            'runtime_sha256': trial_audit['runtime_sha256'],
            'hashes': trial['hashes'],
            'executor': trial['scoped_executor']['stats'],
            'queue': trial['scoped_completion']['stats'],
            'reason': 'zero compiler-admitted deferrable tables; erase dynamic scope queries and split bookkeeping for this program',
        }
    else:
        # Historical negative evidence is frozen; current executable deliberately
        # specializes this rejected route away. Re-running it is not required.
        rejected = json.loads((output / 'scoped-executor-audit.json').read_text())['rejected_unspecialized_overhead']
    assert rejected['hashes'] == new['hashes']
    result = {
        'scope': 'standalone Cell CPU; actual Executor protocol, single thread; no timing or parallel claim',
        'baseline_revision': '9b9300d0',
        'runtime_sha256': audit['runtime_sha256'],
        'program_file_sha256': new['program_file_sha256'],
        'hashes': new['hashes'], 'runs': new['runs'],
        'exact_ordered_semantics_match': True,
        'ordinary_stats_stable_ports_publication_and_queue_counts_match': True,
        'independent_executor_progress': 'verified by two-datatype fixture; not admitted for sum-bits',
        'same_sort_independence_verified': False,
        'global_wait_removed_in_sum_bits': False,
        'scoped_executor': new['scoped_executor'],
        'scoped_completion': new['scoped_completion'],
        'rejected_unspecialized_overhead': rejected,
        'remaining': 'precise container/merge effects, concrete bound Cell-port dependencies, parallel publication/union protocol, workers and full-cost throughput admission',
    }
    (output / 'scoped-executor-audit.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    collect(args.root, args.output)

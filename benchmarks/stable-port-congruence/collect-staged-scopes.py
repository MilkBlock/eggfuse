#!/usr/bin/env python3
"""Retain exact semantics and added-work evidence for matched-rule completion."""
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
        log = (root / f'staged-scopes-{suffix}.log').read_text()
        assert 'test result: FAILED' not in log
        rows = [tuple(map(int, row)) for row in re.findall(
            r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', log)]
        assert rows and sum(row[1] for row in rows) == 0
        validation[suffix] = dict(zip(('passed', 'failed', 'ignored'), map(sum, zip(*rows))))
    minimal = (root / 'staged-scopes-minimal-check.log').read_text()
    assert 'Finished' in minimal and 'error:' not in minimal
    validation['no_default_features'] = 'compile check passed'
    negative = (root / 'staged-scopes-origin-negative.log').read_text()
    assert 'matched_entry_origins_survive_completion_and_publication_before_rhs ... FAILED' in negative
    assert 'index out of bounds: the len is 0 but the index is 0' in negative
    validation['matched_origin_negative_control'] = {
        'mutation': 'temporarily make publication clear matched origins unconditionally',
        'observed_failure': 'sealed cursor index 0 read after its storage was cleared',
        'production_source_restored_and_focused_tests_passed': True,
    }
    write(output / 'staged-scopes-validation.json', validation)

    fixture = read(root / 'staged-completion-fixture.json')
    point = fixture['checkpoint']
    stats = point['executor']['stats']
    assert not point['executor']['global_observer']
    assert point['graph']['pending_tasks'] > 0 and point['seen_b_facts'] == 1
    assert stats['executed_bindings_while_pending'] == 2
    assert stats['rhs_fact_births_while_pending'] == 3
    assert stats['rhs_completions'] == 0
    assert fixture['exact_final_state_and_ordered_bindings']
    for key in ('pending_anchors', 'retained_contexts', 'retained_forwards', 'unpublished_changes'):
        assert fixture['final_executor'][key] == 0
    write(output / 'staged-scopes-fixture.json', fixture)

    audit = read(root / 'staged-scopes-final-audit/results.json')
    lanes = audit['cases']['sum-bits']['lanes']
    control, new = (lanes[k] for k in ('local_congruence', 'staged_scopes'))
    previous = read(output / 'merge-scopes-audit.json')
    assert control['hashes'] == new['hashes'] == previous['hashes']
    assert new['runs'] == 1428 and not new['scoped_executor']['global_observer']
    ordinary_changes = {
        key: {'before': control['stats'].get(key), 'after': value}
        for key, value in new['stats'].items() if value != control['stats'].get(key)
    }
    assert ordinary_changes == {'idle_scheduled_runs': {'before': 769, 'after': 767}}
    stats = new['scoped_executor']['stats']
    assert stats['query_completions'] == 3 and stats['rhs_completions'] == 7
    assert stats['rhs_completions'] == stats['rhs_access_completions'] + stats['rhs_union_completions']
    assert stats['rhs_access_completions'] == 6 and stats['rhs_union_completions'] == 1
    assert stats['query_bindings_while_pending'] == 40
    assert stats['rhs_empty_skips'] == 2
    assert stats['executed_bindings_while_pending'] == stats['rhs_fact_births_while_pending'] == 0
    assert stats['rhs_function_updates_while_pending'] == 0
    changes = {}
    for category in ('port_completion', 'scoped_completion', 'scoped_executor'):
        before, after = previous[category]['stats'], new[category]['stats']
        changes[category] = {
            key: {'before': before.get(key, 0), 'after': value, 'delta': value - before.get(key, 0)}
            for key, value in after.items()
            if isinstance(value, int) and value != before.get(key, 0)
        }
    write(output / 'staged-scopes-audit.json', {
        'scope': 'standalone single-thread Cell CPU Executor; no timing or parallel claim',
        'baseline_revision': '9a5c0a18',
        'runtime_sha256': audit['runtime_sha256'],
        'program_file_sha256': new['program_file_sha256'],
        'runs': new['runs'], 'hashes': new['hashes'],
        'exact_ordered_semantics_match': True,
        'ordinary_runtime_counter_changes_from_global_control': ordinary_changes,
        'admitted_as_performance_improvement': False,
        'port_completion': new['port_completion'],
        'scoped_completion': new['scoped_completion'],
        'scoped_executor': new['scoped_executor'],
        'counter_changes_from_previous_experiment': changes,
        'idle_run_difference': 'Two empty Runs now carry pending work, so they execute the normal empty path instead of the fully-settled idle shortcut. This is added work, not useful independent progress.',
        'remaining': 'bound matched-rule accesses and union effects, same-table regions, proof cost, concurrent union/publication ownership, real workers and full-cost admission',
    })


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    collect(args.root, args.output)

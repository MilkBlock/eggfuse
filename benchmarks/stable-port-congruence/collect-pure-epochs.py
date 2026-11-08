#!/usr/bin/env python3
"""Keep pure-source-epoch semantics, actual writes, and rejected scope costs."""
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
        log = (root / f'pure-epochs-{suffix}.log').read_text()
        assert 'test result: FAILED' not in log
        rows = [tuple(map(int, row)) for row in re.findall(
            r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', log)]
        assert rows and sum(row[1] for row in rows) == 0
        validation[suffix] = dict(zip(('passed', 'failed', 'ignored'), map(sum, zip(*rows))))
    minimal = (root / 'pure-epochs-minimal-check.log').read_text()
    assert 'Finished' in minimal and 'error:' not in minimal
    validation['no_default_features'] = 'compile check passed'
    negative = (root / 'pure-epochs-peer-negative.log').read_text()
    assert 'an_older_task_cannot_backdate_a_collision_with_a_completed_newer_peer ... FAILED' in negative
    assert 'left: 1' in negative and 'right: 2' in negative
    validation['peer_epoch_negative_control'] = {
        'mutation': 'temporarily use the current task epoch without joining the completed peer epoch',
        'observed_failure': 'the final G row is stamped at epoch 1 instead of its causal epoch 2',
        'production_source_restored_and_focused_tests_passed': True,
    }
    write(output / 'pure-epochs-validation.json', validation)

    fixture = read(root / 'pure-epochs-fixture.json')
    point = fixture['checkpoint']
    assert not point['global_observer'] and fixture['pending_tasks_at_checkpoint'] > 0
    assert fixture['consumed_facts_at_checkpoint'] == 1
    assert point['stats']['rhs_fact_births_while_pending'] == 2
    assert point['stats']['source_unions_while_pending'] == 1
    assert fixture['queue']['stats']['mixed_epoch_inserts'] > 0
    assert fixture['exact_final_state_and_ordered_bindings']
    for key in ('pending_anchors', 'retained_contexts', 'retained_forwards', 'unpublished_changes'):
        assert fixture['final_executor'][key] == 0
    write(output / 'pure-epochs-fixture.json', fixture)

    audit = read(root / 'pure-epochs-final-audit/results.json')
    lanes = audit['cases']['sum-bits']['lanes']
    control, previous, new = (lanes[k] for k in ('local_congruence', 'staged_scopes', 'pure_epochs'))
    original = read(output / 'staged-scopes-audit.json')
    assert new['hashes'] == previous['hashes'] == control['hashes'] == original['hashes']
    assert new['runs'] == 1428 and not new['scoped_executor']['global_observer']
    stats = new['scoped_executor']['stats']
    assert stats['bound_rhs_accepts'] == stats['bound_rhs_noop_accepts'] == 3
    assert stats['executed_bindings_while_pending'] == 12
    assert stats['rhs_fact_births_while_pending'] == stats['rhs_function_updates_while_pending'] == stats['source_unions_while_pending'] == 0
    assert stats['query_completions'] == 6 and stats['rhs_completions'] == 4
    ports = new['port_completion']['stats']
    assert ports['pure_epoch_accepts'] == 0 and ports['pure_epoch_boundary_rejections'] == 4
    program = read(root / 'sum-program.json')
    tables = [t['name'] for t in program['recipe']['tables']]
    boundaries = {tables[int(t)]: count for t, count in ports['pure_epoch_boundary_tables'].items()}
    assert boundaries == {'TypeList-length': 4}
    changes = {}
    for category in ('port_completion', 'scoped_completion', 'scoped_executor'):
        before, after = previous[category]['stats'], new[category]['stats']
        changes[category] = {
            key: {'before': before.get(key, 0), 'after': value, 'delta': value - before.get(key, 0)}
            for key, value in after.items()
            if isinstance(value, int) and value != before.get(key, 0)
        }
    ordinary = {
        key: {'before': previous['stats'].get(key), 'after': value}
        for key, value in new['stats'].items() if value != previous['stats'].get(key)
    }
    assert ordinary == {'idle_scheduled_runs': {'before': 767, 'after': 764}}
    assert new['key_lookup_calls'] == previous['key_lookup_calls'] + 25
    conflicts = []
    for line in (root / 'pure-epochs-final-audit/sum-bits-staged_scopes.log').read_text().splitlines():
        if '[cell-cpu] completion-rhs ' in line:
            item = json.loads(line.split('completion-rhs ', 1)[1])
            for rule in item['rules']:
                rule['access_conflicts'] = [[tables[a], tables[b]] for a, b in rule['access_conflicts']]
                rule['all_conflicts'] = [[tables[a], tables[b]] for a, b in rule['all_conflicts']]
            conflicts.append(item)
    assert len(conflicts) == 7 and all(c['ruleset'] == 'type-helpers' for c in conflicts)
    assert {r['rule'] for c in conflicts for r in c['rules']} == {576, 577}
    write(output / 'pure-epochs-audit.json', {
        'scope': 'standalone single-thread Cell CPU Executor; no timing or parallel claim',
        'baseline_revision': 'e30c2e1d', 'runtime_sha256': audit['runtime_sha256'],
        'program_file_sha256': new['program_file_sha256'],
        'runs': new['runs'], 'hashes': new['hashes'],
        'exact_ordered_semantics_match': True,
        'admitted_as_performance_improvement': False,
        'port_completion': new['port_completion'],
        'scoped_completion': new['scoped_completion'],
        'scoped_executor': new['scoped_executor'],
        'ordinary_runtime_counter_changes': ordinary,
        'key_lookup_calls': {'before': previous['key_lookup_calls'], 'after': new['key_lookup_calls']},
        'counter_changes_from_staged_scopes': changes,
        'prior_rhs_conflicts': conflicts,
        'rejected_boundary_tables': boundaries,
        'interpretation': 'All workload admissions are no-op RHSs. No effective union, new fact or function update runs ahead of pending work. Ten completions remain, shifted from three query/seven RHS to six query/four RHS; three more empty Runs lose the settled-idle shortcut.',
        'remaining': 'Distinguish read-only Set inputs, displaced union roots and operator-filtered collision outputs. The current all-root closure can reach TypeList-length through unchanged inputs; the rejection is potential influence, not proof of an actual mutable write. Concurrent ownership, workers and complete-cost admission remain open.',
    })


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    collect(args.root, args.output)

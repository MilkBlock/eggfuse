#!/usr/bin/env python3
"""Retain source-effect completeness, independent mutations, and proof costs."""
import argparse
import json
from pathlib import Path
import re


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def delta(before, after):
    return {k: {'before': before.get(k, 0), 'after': v,
                'delta': v - before.get(k, 0)}
            for k, v in after.items()
            if isinstance(v, int) and v != before.get(k, 0)}


def collect(root, output):
    validation = {}
    for suffix in ('workspace-tests', 'tests', 'non-sparse-tests'):
        log = (root / f'displaced-epochs-{suffix}.log').read_text()
        assert 'test result: FAILED' not in log
        rows = [tuple(map(int, row)) for row in re.findall(
            r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', log)]
        assert rows and sum(row[1] for row in rows) == 0
        validation[suffix] = dict(zip(('passed', 'failed', 'ignored'), map(sum, zip(*rows))))
    minimal = (root / 'displaced-epochs-minimal-check.log').read_text()
    assert 'Finished' in minimal and 'error:' not in minimal
    validation['no_default_features'] = 'compile check passed'
    negative = (root / 'displaced-epochs-peer-negative.log').read_text()
    assert 'unchanged_input_peers_of_the_same_operator_keep_the_mutable_boundary ... FAILED' in negative
    assert 'left: Number(1)' in negative and 'right: 0' in negative
    validation['negative_control'] = {
        'mutation': 'omit shared-wiring candidates on the unchanged source representative',
        'failure': 'a batch with a mutable collision-result consumer is incorrectly admitted',
        'restored_source_passes_focused_suites': True,
        'scope': 'pure admission gate; rejection retains ordinary scoped/eager handling, which may still advance unrelated work',
    }
    fixtures = {}
    positive = {'unrelated-unchanged-user', 'read-only-birth-input'}
    for name in (*sorted(positive), 'same-operator-peer', 'transitive-source-pairs',
                 'future-birth-collision', 'same-key-birth-collision'):
        f = read(root / f'displaced-epochs-fixtures/{name}.json')
        assert not f['checkpoint']['global_observer']
        assert f['admitted'] == (name in positive)
        s = f['checkpoint']['stats']
        assert s['bound_rhs_accepts'] == int(f['admitted'])
        if f['admitted']:
            assert f['pending_tasks'] > 0
        else:
            assert f['ports']['stats']['pure_epoch_boundary_rejections'] > 0
        assert f['exact_final_state_and_ordered_bindings']
        for key in ('pending_anchors', 'retained_contexts', 'retained_forwards', 'unpublished_changes'):
            assert f['final_executor'][key] == 0
        fixtures[name] = {
            'pure_epoch_admitted': f['admitted'], 'pending_tasks': f['pending_tasks'],
            'effective_source_unions_while_pending': s['source_unions_while_pending'],
            'fact_births_while_pending': s['rhs_fact_births_while_pending'],
            'boundary_rejections': f['ports']['stats']['pure_epoch_boundary_rejections'],
            'exact_final_state_and_ordered_bindings': True,
        }
    assert fixtures['unrelated-unchanged-user']['effective_source_unions_while_pending'] == 1
    assert fixtures['read-only-birth-input']['fact_births_while_pending'] == 1
    validation['fixtures'] = fixtures
    write(output / 'displaced-epochs-validation.json', validation)

    audit = read(root / 'displaced-epochs-final-audit/results.json')
    lanes = audit['cases']['sum-bits']['lanes']
    old = read(output / 'pure-epochs-audit.json')
    new = lanes['pure_epochs']
    assert all(lane['hashes'] == old['hashes'] for lane in lanes.values())
    assert new['runs'] == 1428 and not new['scoped_executor']['global_observer']
    s = new['scoped_executor']['stats']
    assert s['bound_rhs_accepts'] == 7 and s['bound_rhs_noop_accepts'] == 3
    assert s['source_unions_while_pending'] == 5 and s['rhs_fact_births_while_pending'] == 6
    assert s['rhs_function_updates_while_pending'] == 0
    assert s['query_completions'] == 6 and s['rhs_completions'] == 0
    assert new['port_completion']['stats']['pure_epoch_boundary_rejections'] == 0
    assert new['port_completion']['stats']['pure_epoch_budget_rejections'] == 0
    assert new['port_completion']['stats']['pure_epoch_accepts'] == 4
    changes = {}
    for category in ('port_completion', 'scoped_completion', 'scoped_executor'):
        changes[category] = delta(old[category]['stats'], new[category]['stats'])
    write(output / 'displaced-epochs-audit.json', {
        'scope': 'standalone single-thread Cell CPU; exact ordered trace audit, not timing',
        'previous_revision': '210b57dd', 'runtime_sha256': audit['runtime_sha256'],
        'program_file_sha256': new['program_file_sha256'], 'runs': new['runs'],
        'hashes': new['hashes'], 'exact_ordered_semantics_match': True,
        'admitted_as_performance_improvement': False,
        'completion_waits': {'previous': 10, 'current': 6, 'query': 6, 'rhs': 0},
        'independent_effective_mutations': {'source_unions': 5, 'fact_births': 6, 'function_updates': 0},
        'port_completion': new['port_completion'],
        'scoped_completion': new['scoped_completion'],
        'scoped_executor': new['scoped_executor'],
        'counter_changes_from_previous_pure_epochs': changes,
        'key_lookup_calls': {'previous': old['key_lookup_calls']['after'], 'current': new['key_lookup_calls']},
        'interpretation': 'Four nontrivial source batches now commit while older congruence is pending. Both collision endpoints remain covered. No full-cost speedup or worker scaling is established.',
        'remaining': 'Six query waits remain; influence walks, bound RHS replay, retained frontiers and publication are still sequential costs. Replace repeated runtime proofs with reusable compiler/Bake facts, then establish concurrent ownership and worker scaling.',
    })


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    collect(args.root, args.output)

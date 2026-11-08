#!/usr/bin/env python3
"""Verify immutable guard extraction without attributing a speedup to it."""
import argparse
import json
from pathlib import Path
import re


def read(path):
    return json.loads(path.read_text())


def collect(root, output):
    validation = {}
    for suffix in ('workspace-tests', 'tests', 'non-sparse-tests'):
        log = (root / f'read-guards-{suffix}.log').read_text()
        assert 'test result: FAILED' not in log
        rows = [tuple(map(int, row)) for row in re.findall(
            r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', log)]
        assert rows and not any(row[1] for row in rows)
        for name in (
            'live_graph_guards_run_on_workers_without_mutating_graph_or_counters',
            'a_new_read_borrow_observes_aliases_and_rejects_retired_instances',
        ):
            assert f'{name} ... ok' in log
        if suffix == 'workspace-tests':
            for name in (
                'shared_multi_input_code_requires_every_equality_and_scalar_guard',
                'compiled_conditions_and_bound_inputs_are_shared_by_scoped_workers',
            ):
                assert f'{name} ... ok' in log
        validation[suffix] = dict(zip(('passed', 'failed', 'ignored'), map(sum, zip(*rows))))
    log = (root / 'read-guards-minimal-check.log').read_text()
    assert 'Finished' in log and 'error:' not in log
    validation['no_default_features'] = 'compile check passed'
    old = read(root / 'unique-publication-final-audit/results.json')
    audit = read(root / 'read-guards-final-audit/results.json')
    before = old['cases']['sum-bits']['lanes']
    after = audit['cases']['sum-bits']['lanes']
    expected = read(output / 'unique-publication-audit.json')['hashes']
    for lane, value in after.items():
        assert value['hashes'] == expected and value['runs'] == 1428
        for field in value:
            if field == 'stage_spine':
                # Profiling clocks are not deterministic work or a timing gate.
                for k, v in value[field].items():
                    if not k.endswith('_seconds'):
                        assert v == before[lane][field][k], (lane, field, k)
            else:
                assert value[field] == before[lane][field], (lane, field)
    pure = after['pure_epochs']
    work = pure['stable_ports']['stats']
    local = pure['stable_ports']['local_conditions']['stats']
    result = {
        'scope': 'standalone Cell CPU; immutable guard kernels integrated into serial runtime',
        'previous_revision': 'a64d43f1',
        'runtime_sha256': audit['runtime_sha256'],
        'program_file_sha256': pure['program_file_sha256'],
        'runs': 1428, 'hashes': expected,
        'exact_ordered_semantics_match': True,
        'all_deterministic_audit_counters_unchanged': True,
        'admitted_as_performance_improvement': False,
        'validation': validation,
        'actual_runtime_path': {
            'key_candidates': work['key_candidates'],
            'key_field_comparisons': work['key_field_comparisons'],
            'local_condition_visits': local['condition_visits'],
            'local_operator_guards': local['operator_guards'],
            'local_equality_guards': local['equality_guards'],
            'local_scalar_guards': local['scalar_guards'],
        },
        'concurrency_evidence': {
            'unit_fixture': 'Two scoped worker threads share one condition, port bindings and equality relation; each returns its own counts.',
            'runtime_graph_fixture': 'Three scoped worker threads evaluate borrowed live-Graph key candidates, rejecting wrong operator/scalar keys without changing Graph counters.',
            'type_checks': 'ReadView, KeyGuard and the immutable condition Plan satisfy Send + Sync without unsafe implementations.',
            'lifetime_fixture': 'A new borrow sees a union through the unchanged port; hidden peers remain eligible and deleted/expired instances are rejected.',
        },
        'limits': 'Executor still calls the kernels serially. Scoped worker execution is verified in fixtures, not integrated worker scheduling. The borrow prevents Graph mutation during reading; there is no asynchronous generation protocol or multithreaded speedup claim.',
        'remaining': 'Batch useful guard/query work without copying Graph or scanning unrelated tables; schedule ready work on persistent workers, preserve candidate/publication order, and account for dispatch, result buffers, allocations and contention before performance admission.',
    }
    (output / 'read-guards-audit.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    collect(args.root, args.output)

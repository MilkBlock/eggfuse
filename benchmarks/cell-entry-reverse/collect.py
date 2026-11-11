#!/usr/bin/env python3
"""Validate saved work diagnostics. Never execute or time a workload."""
import hashlib
import json
from pathlib import Path
import sys


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def signature(report):
    keys = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch',
            'logical_matches', 'executed_bindings', 'changed', 'live_cells')
    rows = [[step[key] for key in keys] for step in report['steps']]
    return hashlib.sha256(json.dumps(rows, separators=(',', ':')).encode()).hexdigest()


def collect(root, output):
    baseline = read(Path(__file__).resolve().parent.parent / 'cell-entry-admission/results.json')
    result = {'baseline_commit': '217e3285',
              'scope': 'standalone Cell CPU; sum-bits and Raytrace prefix work only, no timing',
              'binary_sha256': sha(root / 'runtime-final'), 'cases': {}}
    for case in ('sum', 'ray1280'):
        off, on = [root / (case + '-final-' + mode) for mode in ('off', 'on')]
        a, b = [read(folder / 'report.json') for folder in (off, on)]
        prior = root.parent / 'cell-entry-admission' / (case + '-after')
        # Bind the saved current-branch control to its reviewed observation.
        assert sha(prior / 'report.json') == baseline['cases'][case]['report_sha256'][1]
        c = read(prior / 'report.json')
        assert sha(off / 'state.json') == sha(on / 'state.json') == sha(prior / 'state.json')
        assert signature(a) == signature(b) == signature(c)
        for key in ('stats', 'indexed_columns', 'entry_schedule', 'free_join', 'key_lookup_calls'):
            assert a[key] == b[key] == c[key], (case, key)
        assert a['program_sha256'] == b['program_sha256'] == c['program_sha256']
        control_sieve = a['sieve'].copy()
        control_sieve.pop('reverse')
        prior_sieve = c['sieve'].copy()
        prior_sieve.pop('entry_admission_audit')
        assert control_sieve == prior_sieve
        config = b['prefix_configuration'].copy()
        assert config.pop('requested_cell_entry_reverse') is True
        assert config == a['prefix_configuration'] == c['prefix_configuration']
        old, new = [report['sieve'].copy() for report in (a, b)]
        before, after = [s.pop('reverse') for s in (old, new)]
        assert not before['enabled'] and after['enabled']
        assert all(value == 0 for value in before['stats'].values())
        work = [s.pop('stats').copy() for s in (old, new)]
        assert old == new
        probes = [s.pop('probes') for s in work]
        rejects = [s.pop('rejected') for s in work]
        for s in work:
            s.pop('per_rule')
        assert work[0] == work[1], 'support construction and maintenance must not grow'
        assert probes[1] < probes[0]
        # A dropped row can also avoid earlier passing guards before its rejection.
        earlier_probes = probes[0] - probes[1] - (rejects[0] - rejects[1]) - after['stats']['probes_omitted']
        assert rejects[1] <= rejects[0] and earlier_probes >= 0
        result['cases'][case] = {
            'runs': len(a['steps']), 'state_sha256': sha(on / 'state.json'),
            'run_signature_sha256': signature(b),
            'reports_sha256': [sha(p / 'report.json') for p in (off, on)],
            'sieve_probes': probes, 'sieve_rejected_visits': rejects,
            'earlier_passing_guard_probes_avoided': earlier_probes,
            'reverse': after['stats'], 'free_join_entry_probes': b['free_join']['entry_probes'],
            'graph_effects_and_ordered_runs_equal': True,
            'indexes_entry_free_join_and_support_maintenance_equal': True,
        }
    acceptance = read(root / 'semantic-acceptance.json')
    assert acceptance['status'] == 'pass'
    assert sha(root / 'semantic/run-values/state.json') == result['cases']['sum']['state_sha256']
    result['sum_native_acceptance'] = {'status': 'pass', 'sha256': sha(root / 'semantic-acceptance.json')}
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('validation requires Python assertions; do not use -O')
    collect(Path(sys.argv[1]), Path(sys.argv[2]))

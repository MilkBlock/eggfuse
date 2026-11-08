#!/usr/bin/env python3
"""Retain structural evidence and ordered audits; no timing campaign is run."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def collect(root, output):
    base = Path(__file__).resolve().parents[1]
    compact = module('slice_compact', base / 'local-unions/collect.py').compact
    packing = module('slice_packing', base / 'cell-ownership/collect.py')
    audit = read(root / 'audit-standalone/results.json')
    previous_path = base / 'cell-ownership/audit.json'
    previous = read(previous_path)
    old = previous['cases']['sum-bits']['lanes']['owned']
    current = audit['cases']['sum-bits']['lanes']['slices']
    for key, stamp in old['hashes'].items():
        if key != 'spine-shapes.json':
            assert current['hashes'][key] == stamp, key
    report = current['cell_ownership']
    s = report['stats']
    assert s['owned_live'] == report['inventory']['eligible_live_facts']
    assert report['pending_keys'] == 0
    assert s['boundary_body_reads'] == s['boundary_rebuilds'] == 0
    assert s['port_checks'] == s['changed_ports'] > 0
    assert s['unchanged_port_checks'] == 0
    assert s['slice_steps'] == s['inactive_slice_steps'] + s['coalesced_slice_steps'] + s['body_visits']
    assert s['cross_stage_continuations'] > 0
    for field in ['result_publications', 'key_completions', 'owned_live']:
        assert s[field] == old['cell_ownership']['stats'][field]
    line = next(x for x in (root / 'focused.log').read_text().splitlines()
                if x.startswith('SLICE_EVIDENCE '))
    fixtures = json.loads(line[len('SLICE_EVIDENCE '):])
    fixture_work = [{k: c['stats'][k] for k in
                    ['port_checks', 'changed_ports', 'slice_steps', 'body_visits', 'signal_activations']}
                    for c in fixtures['cases']]
    assert all(x == fixture_work[0] for x in fixture_work)
    monitor = {
        'scope': 'standalone Cell CPU; structural operations, not timing or native egglog performance',
        'parent_revision': 'ee259fd2',
        'parent_audit_file_sha256': hashlib.sha256(previous_path.read_bytes()).hexdigest(),
        'parent_audit_runtime_sha256': previous['runtime_sha256'],
        'boundary_units': {'parent': 'canonical root to lifetime owner',
                           'current': 'canonical root to cross-frame/aliased template symbol'},
        'parent': {'inventory': old['cell_ownership']['inventory'],
                   'stats': old['cell_ownership']['stats'], 'maintenance': old['maintenance']},
        'current': {'inventory': report['inventory'], 'stats': s,
                    'barriers': report['barriers'], 'maintenance': current['maintenance']},
        'comparable_work': {k: {'before': old['cell_ownership']['stats'][k], 'after': s[k]}
                            for k in ['body_visits', 'port_checks', 'boundary_body_reads',
                                      'boundary_insert_attempts', 'key_completions', 'result_publications']},
        'full_ordered_trace_matches_parent': True,
    }
    def save(name, value, keep=False):
        (output / name).write_text(packing.pretty(compact(packing.barriers(value, keep))) + '\n')
    save('audit.json', audit)
    save('monitor.json', monitor, keep=True)
    save('fixtures.json', fixtures)
    save('bake.json', {'scope': 'compiler only; no workload execution',
                      'compiler_sha256': hashlib.sha256((root / 'compiler-final').read_bytes()).hexdigest(),
                      'coverage': read(root / 'baked-sum-final/coverage.json')})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    collect(a.root, a.output)

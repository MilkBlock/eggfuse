#!/usr/bin/env python3
"""Retain structural gates, final small-workload timings and rejected evidence."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def collect(root, output):
    base = Path(__file__).resolve().parents[1]
    compact = module('fragment_compact', base / 'local-unions/collect.py').compact
    packing = module('fragment_packing', base / 'cell-ownership/collect.py')
    timing_collect = module('fragment_timing', base / 'result-port-repair/collect.py').collect
    comparison = module('fragment_admission', base / 'ownership-composition/collect.py').comparison

    def save(name, value, keep=False):
        (output / name).write_text(packing.pretty(compact(packing.barriers(value, keep))) + '\n')

    checks = {}
    for label, filename in (('workspace_all_features', 'workspace-tests-final.log'),
                            ('ownership_sparse', 'focused-final.log'),
                            ('ownership_non_sparse', 'non-sparse-tests-final.log')):
        log = (root / filename).read_text()
        assert 'test result: FAILED' not in log
        counts = [tuple(map(int, m)) for m in re.findall(
            r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', log)]
        assert counts
        totals = dict(zip(('passed', 'failed', 'ignored'), map(sum, zip(*counts))))
        assert totals['failed'] == 0
        checks[label] = totals
    minimal = (root / 'no-default-check-final.log').read_text()
    assert 'Finished' in minimal and 'error:' not in minimal
    checks['runtime_no_default_features'] = 'compile check passed'
    save('validation.json', checks)

    audit = read(root / 'audit-final/results.json')
    previous_path = base / 'ownership-composition/audit.json'
    old = read(previous_path)['cases']['sum-bits']['lanes']['composed']
    lanes = audit['cases']['sum-bits']['lanes']
    report = lanes['fragments']['cell_ownership']
    s = report['stats']
    assert lanes['control']['cell_ownership']['plan_prepared'] is False
    for lane in ('uncomposed', 'fragments'):
        current = lanes[lane]
        for key, stamp in old['hashes'].items():
            if key != 'spine-shapes.json':
                assert current['hashes'][key] == stamp, (lane, key)
        stats = current['cell_ownership']['stats']
        for key in ('composition_shape_builds', 'composition_materializations',
                    'composition_shape_steps', 'marker_anchor_reads',
                    'boundary_body_reads', 'boundary_rebuilds', 'unchanged_port_checks'):
            assert stats[key] == 0, (lane, key)
        assert current['cell_ownership']['pending_keys'] == 0
        assert stats['owned_live'] == current['cell_ownership']['inventory']['eligible_live_facts']
        for key in ('key_completions', 'result_publications', 'owned_live'):
            assert stats[key] == old['cell_ownership']['stats'][key]
    assert s['composition_requests'] == s['composition_baked_hits'] > 0
    assert s['composition_unbaked_fallbacks'] > 0
    save('audit.json', audit)

    fields = ('marker_anchor_reads', 'composition_requests', 'composition_materializations',
              'composition_shape_steps', 'signal_bindings_created', 'signal_bindings_live',
              'boundary_live', 'signal_binding_reads', 'port_checks', 'key_completions')
    save('monitor.json', {
        'scope': 'standalone Cell CPU; structural counts, not native egglog performance',
        'parent_revision': 'c4bad788', 'parent_audit_sha256': digest(previous_path),
        'full_ordered_trace_matches_parent': True,
        'comparison': {k: {'previous': old['cell_ownership']['stats'][k],
                          'uncomposed': lanes['uncomposed']['cell_ownership']['stats'][k],
                          'fragments': s[k]} for k in fields},
        'entry_read_units': 'previous counted source columns; current counts checked Entry receipts; do not subtract these as identical operations',
        'current': {'inventory': report['inventory'], 'stats': s, 'barriers': report['barriers']},
        'control_plan_prepared': False,
    }, keep=True)
    fixtures = {}
    for line in (root / 'focused-final.log').read_text().splitlines():
        for prefix in ('SLICE_EVIDENCE', 'COMPOSITION_EVIDENCE'):
            if line.startswith(prefix + ' '):
                fixtures[prefix] = json.loads(line[len(prefix) + 1:])
    assert len(fixtures) == 2
    save('fixtures.json', fixtures)
    program = read(root / 'baked-sum-final/program.json')
    save('bake.json', {
        'scope': 'Bake consumes a separate observed profile; baking does not execute the workload',
        'compiler_sha256': digest(root / 'compiler-final'),
        'coverage': read(root / 'baked-sum-final/coverage.json'),
        'selection': program['ownership_fragments'],
        'program_bytes': (root / 'baked-sum-final/program.json').stat().st_size,
        'markers_bytes': (root / 'baked-sum-final/markers.json').stat().st_size,
    })
    save('profile.json', read(root / 'profile-sum-final/profile.json'))

    raw_timing = read(root / 'timing-normalized/samples.json')
    timing = timing_collect(raw_timing)
    timing['path_policy'] = raw_timing['path_policy']
    save('timings.json', timing)
    rows = timing['cases']['sum-bits']
    against = {lane: {key: comparison(rows['fragments'], rows[lane], key)
                      for key in ('inference_seconds', 'process_wall_seconds')}
               for lane in ('fast_baseline', 'previous_composed', 'control', 'uncomposed')}
    accepted = all(v['paired_bootstrap_95pct_ratio'][1] < 1
                   for v in against['fast_baseline'].values())
    save('admission.json', {
        'scope': 'sum-bits only; profile and evaluation use the same frozen workload, not held-out generalization',
        'fast_baseline_revision': '8fffff65', 'previous_revision': 'c4bad788',
        'rule': 'semantic audit passes and upper 95% paired bootstrap ratio is below 1 for both inference and process wall versus ordinary fast baseline',
        'accepted_as_acceleration': accepted, 'against': against,
        'control_vs_fast_baseline': {key: comparison(rows['control'], rows['fast_baseline'], key)
                                     for key in ('inference_seconds', 'process_wall_seconds')},
        'caveats': ['one warmup and 31 interleaved fresh-process samples per lane',
                    raw_timing['path_policy'],
                    'normal timing builds exclude allocation and ordered-trace instrumentation',
                    'process wall includes parsing, validation, setup, export and report diagnostics',
                    'training/Bake is separate preprocessing and must be amortized for deployment',
                    'profile alternatives overlap; candidate scores are not total savings'],
    })
    allocation = {'scope': 'allocator requests during execute only; diagnostic binary excluded from timing',
                  'runtime_sha256': digest(root / 'allocation-runtime-final'), 'lanes': {}}
    for lane in ('control', 'uncomposed', 'fragments'):
        r = read(root / f'allocation-final-{lane}/report.json')
        assert r['status'] == 'complete'
        assert r['stats'] == rows[lane]['invariants']['stats']
        assert digest(root / f'allocation-final-{lane}/state.json') == lanes[lane]['hashes']['state.json']
        allocation['lanes'][lane] = r['allocations']
    save('allocations.json', allocation)
    legacy = root / 'timing-final/samples.json'
    if legacy.exists():
        old_timing = read(legacy)
        assert all(old_timing['cases']['sum-bits'][lane]['runtime_sha256'] == row['runtime_sha256']
                   and old_timing['cases']['sum-bits'][lane]['program_file_sha256'] == row['program_file_sha256']
                   for lane, row in raw_timing['cases']['sum-bits'].items())
        save('loading-sensitivity.json', {
            'scope': 'same binaries and input bytes; original versus equal-length command paths',
            'finding': 'cold loading varies with command paths even for identical inputs; allocator/layout mechanism is not established',
            'original_paths': timing_collect(old_timing),
            'equal_length_paths': {lane: {k: v for k, v in row.items() if k.startswith('median_')}
                                   for lane, row in raw_timing['cases']['sum-bits'].items()},
        })


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    collect(args.root, args.output)

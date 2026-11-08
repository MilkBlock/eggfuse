#!/usr/bin/env python3
"""Preserve semantic gates, full-cost diagnostics and small-sample admission.

All reports concern the standalone Cell CPU. Allocation diagnostics never
participate in timing admission; the normal executable has no allocator meters.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import re
import statistics


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def comparison(candidate, baseline, key):
    a = [s[key] for s in candidate['samples']]
    b = [s[key] for s in baseline['samples']]
    assert len(a) == len(b) and len(a) >= 7
    rng = random.Random(20261109)
    ratios = []
    for _ in range(5000):
        ids = rng.choices(range(len(a)), k=len(a))
        ratios.append(statistics.median(a[i] for i in ids) /
                      statistics.median(b[i] for i in ids))
    ratios.sort()
    return dict(candidate_median=statistics.median(a),
                baseline_median=statistics.median(b),
                median_ratio=statistics.median(a) / statistics.median(b),
                paired_bootstrap_95pct_ratio=[ratios[124], ratios[4874]])


def collect(root, output):
    base = Path(__file__).resolve().parents[1]
    compact = module('composition_compact', base / 'local-unions/collect.py').compact
    packing = module('composition_packing', base / 'cell-ownership/collect.py')
    timing_collect = module('composition_timing', base / 'result-port-repair/collect.py').collect

    def save(name, value, keep=False):
        (output / name).write_text(packing.pretty(compact(packing.barriers(value, keep))) + '\n')

    checks = {}
    for label, filename in (('workspace_all_features', 'workspace-tests.log'),
                            ('ownership_sparse', 'focused.log'),
                            ('ownership_non_sparse', 'non-sparse-tests.log')):
        log = (root / filename).read_text()
        assert 'test result: FAILED' not in log
        counts = [tuple(map(int, m)) for m in re.findall(
            r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', log)]
        assert counts
        totals = dict(zip(('passed', 'failed', 'ignored'), map(sum, zip(*counts))))
        assert totals['failed'] == 0
        checks[label] = totals
    minimal = (root / 'no-default-check.log').read_text()
    assert 'Finished' in minimal and 'error:' not in minimal
    checks['runtime_no_default_features'] = 'compile check passed'
    save('validation.json', checks)

    audit = read(root / 'audit-final/results.json')
    previous_path = base / 'ownership-slices/audit.json'
    previous = read(previous_path)
    old = previous['cases']['sum-bits']['lanes']['slices']
    lanes = audit['cases']['sum-bits']['lanes']
    current = lanes['composed']
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
    assert s['composition_requests'] > 0
    for field in ('result_publications', 'key_completions', 'owned_live'):
        assert s[field] == old['cell_ownership']['stats'][field]
    save('audit.json', audit)
    fixtures = {}
    for line in (root / 'focused.log').read_text().splitlines():
        for prefix in ('SLICE_EVIDENCE', 'COMPOSITION_EVIDENCE'):
            if line.startswith(prefix + ' '):
                fixtures[prefix] = json.loads(line[len(prefix) + 1:])
    assert len(fixtures) == 2
    save('fixtures.json', fixtures)
    fields = ('signal_bindings_created', 'signal_bindings_live', 'boundary_live',
              'boundary_insert_attempts', 'signal_binding_reads', 'port_checks',
              'key_completions', 'result_publications')
    save('monitor.json', {
        'scope': 'standalone Cell CPU; operation counts, not native egglog performance',
        'parent_revision': '347e4aa3',
        'parent_audit_sha256': digest(previous_path),
        'full_ordered_trace_matches_parent': True,
        'boundary_units': {'parent': 'canonical root to template symbol',
                           'current': 'canonical root to external composed symbol'},
        'comparison_to_slices': {k: {'before': old['cell_ownership']['stats'][k], 'after': s[k]}
                                 for k in fields},
        'current': {'inventory': report['inventory'], 'stats': s, 'barriers': report['barriers']},
        'ordinary_control': {'maintenance': lanes['control']['maintenance'],
                             'repair_ports': lanes['control']['repair_ports']},
        'remaining_costs': ['component/frame bookkeeping and checked Entry lookups',
                            'cold shape expansion and retained cached shapes',
                            'external boundary index and signal lifetime maintenance',
                            'ordered heap merge and exact congruence key probes'],
    }, keep=True)
    save('bake.json', {
        'scope': 'compiler only; compact recipes with cold runtime shape materialization',
        'compiler_sha256': digest(root / 'compiler-final'),
        'coverage': read(root / 'baked-sum-final/coverage.json'),
        'program_bytes': (root / 'baked-sum-final/program.json').stat().st_size,
        'markers_bytes': (root / 'baked-sum-final/markers.json').stat().st_size,
    })
    timing = timing_collect(read(root / 'timing-final/samples.json'))
    save('timings.json', timing)
    rows = timing['cases']['sum-bits']
    against_fast = {key: comparison(rows['composed'], rows['fast_baseline'], key)
                    for key in ('inference_seconds', 'process_wall_seconds')}
    against_control = {key: comparison(rows['composed'], rows['control'], key)
                       for key in ('inference_seconds', 'load_setup_inference_seconds', 'process_wall_seconds')}
    accepted = all(v['paired_bootstrap_95pct_ratio'][1] < 1 for v in against_fast.values())
    save('admission.json', {
        'scope': 'sum-bits only; normal release builds, one warmup and interleaved fresh processes',
        'fast_baseline_revision': '8fffff65',
        'fast_baseline_args': ['--repair-ports', '--entry-publications'],
        'rule': 'semantic audit passes and upper 95% paired bootstrap ratio is below 1 for both inference and process wall versus ordinary fast baseline',
        'accepted_as_acceleration': accepted,
        'against_fast_baseline': against_fast,
        'against_same_binary_control': against_control,
        'caveats': ['small sample and one workload; no generalization to larger workloads',
                    'process wall includes parsing, validation, setup, export and report diagnostics',
                    'archived fast baseline lacks separate load_seconds; never treat its setup as loading',
                    'operation counts are diagnostic evidence, not time-calibrated credit'],
    })
    allocation = {'scope': 'allocator request accounting during execute only; separate diagnostic build; no timing claims',
                  'runtime_sha256': digest(root / 'allocation-runtime-final'), 'lanes': {}}
    for lane in ('control', 'composed'):
        r = read(root / f'allocation-{lane}/report.json')
        assert r['status'] == 'complete'
        assert r['stats'] == rows[lane]['invariants']['stats']
        assert digest(root / f'allocation-{lane}/state.json') == current['hashes']['state.json']
        allocation['lanes'][lane] = r['allocations']
    save('allocations.json', allocation)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    collect(args.root, args.output)

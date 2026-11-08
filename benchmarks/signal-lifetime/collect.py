#!/usr/bin/env python3
"""Retain exact semantics, operation costs and the two-workload admission gate."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import statistics


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def collect(root, output):
    base = Path(__file__).resolve().parents[1]
    compact = module('lifetime_compact', base / 'local-unions/collect.py').compact
    packing = module('lifetime_packing', base / 'cell-ownership/collect.py')
    timing_collect = module('lifetime_timing', base / 'result-port-repair/collect.py').collect
    compare = module('lifetime_admission', base / 'ownership-composition/collect.py').comparison

    def save(name, value, keep=False):
        (output / name).write_text(packing.pretty(compact(packing.barriers(value, keep))) + '\n')

    validation = {}
    for name, log_name in [('workspace_all_features', 'workspace-tests.log'),
                           ('ownership_sparse', 'focused-final.log'),
                           ('ownership_non_sparse', 'non-sparse-tests.log')]:
        log = (root / log_name).read_text()
        assert 'test result: FAILED' not in log
        counts = [tuple(map(int, row)) for row in re.findall(
            r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', log)]
        assert counts
        validation[name] = dict(zip(('passed', 'failed', 'ignored'), map(sum, zip(*counts))))
    log = (root / 'no-default-check.log').read_text()
    assert 'Finished' in log and 'error:' not in log
    validation['runtime_no_default_features'] = 'compile check passed'
    save('validation.json', validation)

    audit, before = read(root / 'audit/results.json'), read(root / 'audit-before/results.json')
    monitor = {'scope': 'standalone Cell CPU; no native egglog performance claim',
               'before_revision': '5ffdec1d',
               'counter_units': {
                   'signal_binding_reads': 'attach/detach slot accesses, not all hash queries; after uses direct slots',
                   'signal_bindings_live': 'before: bindings with live users; after: all initialized slots retained by live components',
                   'active_signal_bindings': 'after-only inventory reconstructs live users from existing facts outside inference',
                   'component_signal_retire_visits': 'every allocated logical slot scanned during final component retirement, including uninitialized slots',
                   'domain_planning_slice_steps': 'existing fact liveness checks used to derive exact candidate counts on demand'},
               'cases': {}}
    for case, entry in audit['cases'].items():
        a = before['cases'][case]['lanes']['before']
        b = entry['lanes']['slots']
        for key, stamp in a['hashes'].items():
            assert b['hashes'][key] == stamp, (case, key)
        ar, br = a['cell_ownership'], b['cell_ownership']
        sa, sb = ar['stats'], br['stats']
        assert sb['signal_port_detaches'] == 0
        assert sb['signal_binding_reads'] == sb['signal_port_attaches']
        assert sa['signal_binding_reads'] == sa['signal_port_attaches'] + sa['signal_port_detaches']
        assert br['inventory']['active_signal_bindings'] == sa['signal_bindings_live']
        for key in ('owned_live', 'key_completions', 'result_publications', 'port_checks',
                    'composition_requests', 'composition_baked_hits'):
            assert sb[key] == sa[key], (case, key)
        for key in ('composition_shape_builds', 'composition_materializations', 'composition_shape_steps'):
            assert sb[key] == 0
        assert br['pending_keys'] == 0
        monitor['cases'][case] = {'before': ar, 'slots': br, 'all_ordered_hashes_equal': True}
    save('audit.json', audit)
    save('audit-before.json', before)
    save('monitor.json', monitor, keep=True)

    admission = {'scope': 'standalone Cell CPU; identical baked artifacts for before/after; no added descriptors',
                 'before_revision': '5ffdec1d', 'ordinary_fast_baseline_revision': '8fffff65',
                 'rule': 'exact audit and upper 95% paired bootstrap ratio below one for inference and process wall on both sum-bits and Raytrace',
                 'cases': {}}
    allocations = {'scope': 'execute allocator requests; separate diagnostic binaries; excludes setup/export; not RSS',
                   'before_runtime_sha256': digest(root / 'baseline-allocation-runtime'),
                   'slots_runtime_sha256': digest(root / 'allocation-runtime'), 'cases': {}}
    for case in ('sum-bits', 'raytrace'):
        timing = timing_collect(read(root / f'timing-{case}/samples.json'))
        save(f'timings-{case}.json', timing)
        rows = timing['cases'][case]
        assert rows['before']['program_file_sha256'] == rows['slots']['program_file_sha256']
        admission['cases'][case] = {
            'against_before': {key: compare(rows['slots'], rows['before'], key)
                               for key in ('inference_seconds', 'process_wall_seconds')},
            'against_ordinary_fast': {key: compare(rows['slots'], rows['fast_baseline'], key)
                                      for key in ('inference_seconds', 'process_wall_seconds')}}
        phases = ('load_seconds', 'setup_seconds', 'inference_seconds', 'export_seconds')
        admission['cases'][case]['phase_medians'] = {
            lane: {**{key: statistics.median(s[key] for s in rows[lane]['samples']) for key in phases},
                   'unattributed_wall_seconds': statistics.median(
                       s['process_wall_seconds'] - sum(s[key] for key in phases)
                       for s in rows[lane]['samples'])}
            for lane in ('before', 'slots')}
        allocations['cases'][case] = {}
        for lane in ('before', 'slots'):
            report = read(root / f'allocation-{case}-{lane}/report.json')
            assert report['stats'] == rows[lane]['invariants']['stats']
            assert digest(root / f'allocation-{case}-{lane}/state.json') == rows[lane]['invariants']['state_file_sha256']
            allocations['cases'][case][lane] = report['allocations']
    admission['accepted_over_before'] = all(
        metric['paired_bootstrap_95pct_ratio'][1] < 1
        for case in admission['cases'].values() for metric in case['against_before'].values())
    admission['accepted_over_ordinary_fast'] = all(
        metric['paired_bootstrap_95pct_ratio'][1] < 1
        for case in admission['cases'].values() for metric in case['against_ordinary_fast'].values())
    admission['caveats'] = [
        'equal-length executable/input symlinks and numeric output paths; fresh processes interleaved',
        'process wall includes loading, validation, setup, export and report diagnostics',
        'sum-bits uses 31 samples per lane; Raytrace uses 7; one warmup each',
        'profiling and Bake are offline, shared between before/after, excluded from runtime timing',
        'candidate counts derive exact active references only when requested; their extra slice scans are charged',
        'retained inactive slots and boundaries may increase empty dispatch work']
    admission['caveats'].append('unattributed wall time includes reporting, serialization, teardown and process overhead; it is not an inference metric')
    save('admission.json', admission)
    save('allocations.json', allocations)
    save('bake.json', {'scope': 'Raytrace v4 artifact prepared by the unchanged 5ffdec1d compiler for both runtime versions',
                       'coverage': read(root / 'baked-raytrace/coverage.json'),
                       'program_sha256': digest(root / 'baked-raytrace/program.json'),
                       'profile_sha256': digest(root / 'profile-raytrace/profile.json')})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    collect(args.root, args.output)

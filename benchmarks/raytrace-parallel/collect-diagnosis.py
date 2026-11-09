#!/usr/bin/env python3
"""Freeze the bounded Raytrace diagnosis and constructor-lookup repair evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def prefix(path):
    d = read(path)
    initial = d['initial_counters']
    groups = [('stats', 'stats'), ('stable_ports', 'stable_ports_stats'),
              ('cell_ownership_stats', 'cell_ownership_stats')]
    result = {k: d[k] for k in ('mode', 'run_limit', 'completed_runs', 'diagnostic_elapsed_seconds',
                                'state_sha256', 'schedule_sha256', 'source_stage_counts')}
    result['execution_key_lookup_calls'] = d['key_lookup_calls'] - initial['key_lookup_calls']
    for source, target in groups:
        values = d[source]
        if source == 'stable_ports':
            values = values.get('stats')
        result[target] = {k: v - (initial[target] or {}).get(k, 0)
                          for k, v in (values or {}).items()
                          if type(v) is int and (k.startswith('domain_') or k in
                             ('birth_hint_probes', 'birth_hint_hits', 'key_lookups', 'key_candidates',
                              'port_domain_probes', 'merge_program_constructs', 'constructor_requests',
                              'constructor_reused'))}
    return result


def collect(root, output):
    old = read(root / 'metadata.json')
    fixed = read(root / 'fixed-metadata.json')
    assert old['build_source_vs_revision_mismatches'] == []
    metadata = {'scope': 'standalone Cell CPU; not native egglog',
                'base_commit': fixed['base_commit'], 'archived_fast_commit': '8fffff65',
                'features': old['features'], 'rustc': old['rustc'], 'os': old['os'],
                'machine': old['machine'], 'baseline_tag': fixed['baseline_tag'],
                'pre_fix_source_matches_base_commit': True,
                'pre_fix_source_files': old['runtime_source_files'],
                'fixed_runtime_changed_files': {p: fixed['runtime_source_files'][p]
                    for p in fixed['changed_runtime_files']},
                'fixed_runtime_source_sha256': fixed['runtime_source_sha256'],
                'normal_binaries': fixed['binaries'],
                'allocator_features': old['features'] + ['slot-transfer-audit', 'spine-shapes', 'allocation-metrics'],
                'fixed_allocator_binary_sha256': sha(root / 'runtime-fixed-allocator'),
                'measurement_harness_sha256': sha(output / 'measure.py'),
                'cpu_policy': 'No affinity; parent avoided Cargo and CPU-heavy work during timing. Normal macOS background services remained.'}
    save(output / 'metadata.json', metadata)

    diagnosis = {'scope': metadata['scope'], 'prefix_scope': '256 source Runs, not full Raytrace performance',
                 'before_prefix': {}, 'fixed_prefix': {}}
    for name in ('fast', 'local', 'overlap2', 'overlap4'):
        before = prefix(root / 'prefix-256' / f'{name}.json')
        after = prefix(root / 'prefix-fixed-256' / f'{name}.json')
        assert (before['state_sha256'], before['schedule_sha256']) == (after['state_sha256'], after['schedule_sha256'])
        diagnosis['before_prefix'][name] = before
        diagnosis['fixed_prefix'][name] = after
    pilot = read(root / 'fixed-pilot/samples.json')
    diagnosis['completed_parallel_pilot'] = pilot
    diagnosis['parallel_pilot_limit'] = ('One observation per lane, no speedup confidence interval. '
        'Original process waiter can add up to 50 ms polling delay; use final serial timing for accurate wall comparisons. '
        'Guard reads execute on workers; matching, publication and effects retain one writer. Pure epochs are disabled.')
    diagnosis['pre_fix_serial_timeout'] = read(root / 'serial-control/samples.json')['failure']
    diagnosis['pre_fix_serial_timeout']['last_entered_source_run'] = 16529
    diagnosis['pre_fix_serial_timeout']['progress_logging'] = True
    diagnosis['pre_fix_parallel_timeout'] = {'seconds': 180, 'args': ['--guard-workers', '4', '--completion-batch-tasks', '16', '--overlap-completion'],
        'state': 'child killed and waited after timeout; no final report',
        'log_sha256': sha(root / 'pilot.log'), 'sample_seconds': 1,
        'sample_path': str(root / 'pilot-overlap4.sample.txt'), 'sample_sha256': sha(root / 'pilot-overlap4.sample.txt'),
        'sample_main_thread_samples': 92, 'sample_lookup_port_key_samples': 92,
        'sample_owned_candidates_samples': 91, 'sample_dynamic_first_lookup': 41,
        'sample_dynamic_second_lookup': 44, 'guard_threads_parked_during_sample': 4,
        'contemporaneous_ps': {'elapsed_seconds': 152, 'cpu_seconds': 152.43, 'percent_cpu': 99.0, 'rss_kib': 1975776},
        'limit': 'A one-second diagnostic snapshot, not proof of whole-run utilization or deadlock.'}
    diagnosis['bake_replay_limit'] = ('At d03b69e9 iterative Bake did not configure stable ports, port keys, local congruence or pure epochs. '
        'The work ledger therefore did not imply training on this new execution path. No artifact was retrained for this experiment.')
    save(output / 'diagnosis.json', diagnosis)

    allocations = {'scope': 'Separate allocator and ordered-effect audit executable; no diagnostic timings admitted', 'cases': {}}
    for stage in ('before-audit', 'fix-audit'):
        audit = read(root / stage / 'results.json')
        allocations[stage + '_runtime_sha256'] = audit['runtime_sha256']
        for case, data in audit['cases'].items():
            target = allocations['cases'].setdefault(case, {})
            for lane, result in data['lanes'].items():
                report = read(root / stage / f'{case}-{lane}' / 'report.json')
                target[f'{stage}/{lane}'] = {'program_file_sha256': result['program_file_sha256'],
                    'args': result['args'], 'runs': result['runs'], 'hashes': result['hashes'],
                    'allocations': report['allocations'], 'key_lookup_calls': report['key_lookup_calls']}
            comparable = [{k: v for k, v in x['hashes'].items() if k != 'spine-shapes.json'} for x in target.values()]
            assert all(x == comparable[0] for x in comparable)
    allocations['limit'] = 'No completed pre-fix local Raytrace allocator run: it was already over the normal 180 s cap. Fixed local is also compared to fixed fast; requested allocation bytes are not RSS.'
    save(output / 'allocations-audit.json', allocations)
    tests = {}
    for name in ('fix-focused-tests.log', 'fix-workspace-tests.log', 'fix-non-sparse-tests.log'):
        log = root / name
        counts = re.findall(r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', log.read_text())
        assert counts and not any(int(row[1]) for row in counts)
        tests[name] = {k: sum(int(row[i]) for row in counts) for i, k in enumerate(('passed', 'failed', 'ignored'))}
        tests[name]['log_sha256'] = sha(log)
    tests['no_default_features_check'] = {'passed': 'Finished' in (root / 'fix-minimal-check.log').read_text(),
                                         'log_sha256': sha(root / 'fix-minimal-check.log')}
    save(output / 'validation.json', tests)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    collect(args.root, args.output)

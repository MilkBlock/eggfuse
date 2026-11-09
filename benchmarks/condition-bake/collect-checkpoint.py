#!/usr/bin/env python3
"""Validate a shared-code semantic/cost checkpoint without admitting its timing."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(root, output):
    metadata = read(root / 'checkpoint-metadata.json')
    assert metadata.get('finished_at_utc')
    assert metadata['runtime_sources_unchanged_during_checks_and_build']
    assert not any(path.endswith('/parent_absence.rs') for path in metadata['runtime_source_files'])
    checks = {}
    for log, command in metadata['check_commands'].items():
        text = (root / log).read_text()
        matches = re.findall(r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', text)
        entry = {'command': command, 'log_sha256': sha(root / log), 'passed': 'Finished' in text}
        if 'test' in command:
            assert matches and not any(int(row[1]) for row in matches)
            entry['tests'] = {key: sum(int(row[i]) for row in matches)
                              for i, key in enumerate(('passed', 'failed', 'ignored'))}
        assert entry['passed']
        checks[log] = entry

    records = {name: read(root / f'checkpoint-{name}-audit/results.json')
               for name in ('baseline', 'code')}
    assert records['baseline']['runtime_sha256'] == metadata['baseline_allocator_sha256']
    assert records['code']['runtime_sha256'] == metadata['code_allocator_sha256']
    cases = {}
    for case in ('sum-bits', 'raytrace'):
        lanes = {}
        for name in ('baseline', 'code'):
            record = records[name]['cases'][case]['lanes']['local']
            report = read(root / f'checkpoint-{name}-audit/{case}-local/report.json')
            lanes[name] = {'args': record['args'], 'program_file_sha256': record['program_file_sha256'],
                           'runs': record['runs'], 'hashes': record['hashes'],
                           'allocations': report['allocations'],
                           'key_lookup_calls': report['key_lookup_calls'],
                           'cell_ownership_stats': report['cell_ownership']['stats'],
                           'stable_ports_stats': report['stable_ports']['stats'],
                           'local_conditions': report['stable_ports']['local_conditions']}
        before, after = lanes['baseline'], lanes['code']
        assert before['program_file_sha256'] == after['program_file_sha256']
        assert before['runs'] == after['runs']
        # Same artifact: even the unmodified Spine file must match, in addition
        # to its program-independent shape hash and all ordered-effect hashes.
        assert before['hashes'] == after['hashes'], case
        delta = {key: {'before': before['allocations'][key], 'after': after['allocations'][key],
                       'delta': after['allocations'][key] - before['allocations'][key],
                       'ratio': after['allocations'][key] / before['allocations'][key]}
                 for key in ('alloc_calls', 'realloc_calls', 'requested_bytes')}
        cases[case] = {'exact_ordered_hashes_match': True, 'lanes': lanes, 'allocation_comparison': delta}

    bases = {'columns': 'd03b69e9', 'typed': 'ff5e6bc4', 'marker': 'ff5e6bc4', 'absence': 'ff5e6bc4'}
    patches = {path.name: {'clean_base_commit': bases[path.stem], 'sha256': sha(path),
                           'bytes': path.stat().st_size,
                           'variant_status': 'withdrawn' if path.stem == 'absence' else 'historical ablation'}
               for path in sorted((output / 'candidates').glob('*.patch'))}
    result = {'scope': 'standalone Cell CPU; semantic and allocation checkpoint, not native egglog or timing admission',
              'runtime_variant': 'retained shared-code; absence proof withdrawn',
              'normal_runtime_sha256': sha(root / 'runtime-code'),
              'allocator_runtime_sha256': metadata['code_allocator_sha256'],
              'baseline_allocator_sha256': metadata['baseline_allocator_sha256'],
              'allocator_features': metadata['allocator_features'], 'checks': checks, 'cases': cases,
              'normal_performance_gate_passed': False,
              'gate_reason': 'The normal shared-code experiment improved inference but regressed sum-bits whole-process time; diagnostic builds cannot override that result.',
              'candidate_source_patches': patches,
              'limits': 'Allocator counts cover execute and include ordered-audit instrumentation equally in both lanes. Requested bytes are not RSS. Static shared-code slots are storage, not work saved. Logical matches are not committed mutations. No diagnostic timings are admitted.'}
    (output / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
    (output / 'checkpoint-metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    collect(args.root, args.output)

#!/usr/bin/env python3
"""Validate final ordered effects and costs; diagnostic timings are not admitted."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare_audits(root):
    records = {name: read(root / f'{name}-audit/results.json') for name in ('baseline', 'final')}
    cases = {}
    for case in ('sum-bits', 'raytrace'):
        lanes = {}
        for name in ('baseline', 'final'):
            row = records[name]['cases'][case]['lanes']['local']
            report = read(root / f'{name}-audit/{case}-local/report.json')
            assert report['status'] == 'complete'
            lanes[name] = {'runtime_sha256': records[name]['runtime_sha256'],
                           'program_file_sha256': row['program_file_sha256'],
                           'args': row['args'], 'runs': row['runs'], 'hashes': row['hashes'],
                           'allocations': report['allocations'],
                           'setup_allocations': report.get('setup_allocations'),
                           'stats': report['stats'], 'key_lookup_calls': report['key_lookup_calls'],
                           'cell_ownership_stats': report['cell_ownership']['stats'],
                           'stable_ports_stats': report['stable_ports']['stats'],
                           'stage_spine_stats': {k: v for k, v in report['stage_spine']['stats'].items() if not k.endswith('_seconds')}}
        before, after = lanes['baseline'], lanes['final']
        assert before['args'] == after['args'] == ['--local-congruence']
        assert before['runs'] == after['runs'] == (1428 if case == 'sum-bits' else 16883)
        # Classified artifacts have a different program hash. Exclude that
        # one metadata field through the audit helper's canonical shape hash;
        # state and ordered RHS/writes/resumes/schedule remain exact hashes.
        hashes = lambda lane: {key: value for key, value in lane['hashes'].items() if key != 'spine-shapes.json'}
        assert hashes(before) == hashes(after), (case, hashes(before), hashes(after))
        delta = {key: {'before': before['allocations'][key], 'after': after['allocations'][key],
                       'delta': after['allocations'][key] - before['allocations'][key],
                       'ratio': after['allocations'][key] / before['allocations'][key]}
                 for key in ('alloc_calls', 'realloc_calls', 'requested_bytes')}
        cases[case] = {'exact_ordered_hashes_match': True, 'lanes': lanes, 'execute_allocation_comparison': delta}
        if before['setup_allocations'] is not None and after['setup_allocations'] is not None:
            cases[case]['setup_allocation_comparison'] = {
                key: {'before': before['setup_allocations'][key], 'after': after['setup_allocations'][key],
                      'delta': after['setup_allocations'][key] - before['setup_allocations'][key]}
                for key in ('alloc_calls', 'realloc_calls', 'requested_bytes', 'live_bytes_before', 'live_bytes_after')}
    return cases


def collect(root, output):
    metadata = read(root / 'audit-metadata.json')
    assert metadata.get('finished_at_utc') and metadata['source_unchanged']
    cases = compare_audits(root)
    for case in cases.values():
        for name in ('baseline', 'final'):
            assert case['lanes'][name]['runtime_sha256'] == metadata[f'{name}_allocator_sha256']
    checks = {}
    for name, settings in metadata['checks'].items():
        path = Path(settings['log'])
        text = path.read_text()
        assert 'Finished' in text and 'test result: FAILED' not in text
        row = {**settings, 'log_sha256': sha(path)}
        counts = [tuple(map(int, m)) for m in re.findall(r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', text)]
        if counts:
            assert not any(c[1] for c in counts)
            row['tests'] = {key: sum(c[i] for c in counts) for i, key in enumerate(('passed', 'failed', 'ignored'))}
        checks[name] = row
    patches = {p.name: {'base_commit': '86800d89', 'sha256': sha(p), 'bytes': p.stat().st_size}
               for p in sorted((output.parent / 'candidates').glob('*.patch'))}
    validation = {'scope': 'standalone Cell CPU; full ordered-effects and allocator audit, not timing admission',
                  'normal_performance_gate_passed': False,
                  'gate_reason': 'No demonstrated sum-bits whole-process improvement; archived-fast remains faster.',
                  'source_base': '86800d89', 'diagnostic_metadata': metadata,
                  'checks': checks, 'cases': cases, 'source_patches': patches,
                  'limits': 'Execution allocation counters include identical ordered-audit instrumentation in both lanes and exclude setup/export. Requested bytes are not RSS. Missing baseline setup counters are not zero. Only the program_sha256 metadata field is excluded from Spine comparison; all other ordered outputs remain exact. No diagnostic elapsed time is used to claim speedup.'}
    (output / 'validation.json').write_text(json.dumps(validation, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('raw_root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    collect(args.raw_root, args.output)

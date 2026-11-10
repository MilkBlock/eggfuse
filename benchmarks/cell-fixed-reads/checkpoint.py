#!/usr/bin/env python3
"""Collect the five-implementation speed checkpoint from frozen process samples."""
import hashlib
import json
from pathlib import Path
import runpy
import sys

HERE = Path(__file__).resolve().parent
helpers = runpy.run_path(str(HERE.parent / 'raytrace-parallel' / 'collect.py'))
distribution, paired_ratio = helpers['distribution'], helpers['paired_ratio']


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def collect(root, output):
    result = {'provenance': read(root / 'provenance.json'), 'workloads': {},
        'limits': 'Standalone Cell CPU; no general sparsity proof or independent native Raytrace proof. Five Raytrace and seven sum-bits interleaved samples. Paired bootstrap intervals do not establish cross-machine gains. No simultaneous compilation or source edits.'}
    for case, count in [('sum', 1428), ('ray', 16883)]:
        source = root / case / 'samples.json'
        samples = read(source)
        require(samples.get('finished_at_utc') and not samples.get('failure'), case + ' unfinished campaign')
        lanes = samples['lanes']
        require(len({v['program_file_sha256'] for v in lanes.values()}) == 1, case + ' unequal inputs')
        summary = {'raw_samples_sha256': sha(source), 'repeat': samples['repeat'], 'warmups': samples['warmups'],
            'started_at_utc': samples['started_at_utc'], 'finished_at_utc': samples['finished_at_utc'],
            'semantic_reference': samples['semantic_reference'], 'lanes': {}, 'comparisons': {}}
        ordered = {}
        for name, lane in lanes.items():
            rows = sorted(lane['samples'], key=lambda r: r['iteration'])
            require([r['iteration'] for r in rows] == list(range(samples['repeat'])), name + ' sample loss')
            for row in [*lane['warmup_samples'], *rows]:
                require(row['runs'] == count and all(row[k] == v for k, v in samples['semantic_reference'].items()), name + ' semantic difference')
                require(row.get('allocations') is None, name + ' instrumentation')
                w = row.get('query_workers') or {}
                if w.get('enabled'):
                    q = w['stats']
                    require(q['entries'] == q['coordinator_entries'] + sum(q['worker_entries']), name + ' worker ownership')
                    if name.startswith('current_'):
                        require(q['fixed_read_fills'] == q['fixed_read_clears'], name + ' uncleared results')
            ordered[name] = rows
            first = rows[0]
            summary['lanes'][name] = {'runtime_sha256': lane['runtime_sha256'], 'program_file_sha256': lane['program_file_sha256'],
                'args': lane['args'], 'timing': {k: (distribution([r[k] for r in rows]) if all(k in r for r in rows) else None) for k in ['inference_seconds', 'process_wall_seconds', 'load_seconds', 'setup_seconds', 'peak_rss_through_inference_bytes']},
                'phases': {k: distribution([r['phases'][k] for r in rows]) for k in first['phases']},
                'first_sample_work': {k: first.get(k) for k in ['key_lookup_calls', 'stats', 'query_workers', 'stage_spine_stats']},
                'samples': [{k: r[k] for k in ['iteration', 'inference_seconds', 'process_wall_seconds', 'process_user_seconds', 'process_system_seconds']} for r in rows]}
        for base, trial in [('parent_workers', 'current_workers'), ('current_serial', 'current_workers'), ('current_serial', 'current_inline'), ('fast_archived', 'current_serial'), ('fast_archived', 'current_workers')]:
            summary['comparisons'][trial + '_over_' + base] = {k: paired_ratio([r[k] for r in ordered[base]], [r[k] for r in ordered[trial]]) for k in ['inference_seconds', 'process_wall_seconds']}
        for before, after in zip(ordered['parent_workers'], ordered['current_workers']):
            q = after['query_workers']['stats']
            require(before['key_lookup_calls'] - after['key_lookup_calls'] == q['fixed_read_hits'], case + ' saved lookup accounting')
        result['workloads'][case] = summary
    # Link the complete timed sum-bits graph to the separately accepted native
    # comparison, rather than relying only on agreement between CPU versions.
    acceptance = read(root.parent / 'semantic-acceptance.json')
    require(acceptance['status'] == 'pass', 'native sum-bits acceptance')
    require(result['workloads']['sum']['semantic_reference']['state_sha256'] == sha(root.parent / 'sum-after4' / 'state.json'), 'timed sum graph is not the accepted export')
    result['semantic_acceptance_sha256'] = sha(root.parent / 'semantic-acceptance.json')
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({case: {name: {k: v['timing'][k]['median'] for k in ['inference_seconds', 'process_wall_seconds']} for name, v in summary['lanes'].items()} for case, summary in result['workloads'].items()}, indent=2))


if __name__ == '__main__':
    collect(Path(sys.argv[1]), Path(sys.argv[2]))

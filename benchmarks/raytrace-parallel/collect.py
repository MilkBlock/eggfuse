#!/usr/bin/env python3
"""Summarize paired Raytrace wall/inference observations and actual worker work."""
import argparse
import json
from pathlib import Path
import random
import statistics


def distribution(values):
    median = statistics.median(values)
    return {'median': median, 'minimum': min(values), 'maximum': max(values),
            'median_absolute_deviation': statistics.median(abs(value - median) for value in values)}


def paired_ratio(reference, trial):
    assert len(reference) == len(trial) and reference
    pairs = [trial[i] / reference[i] for i in range(len(reference))]
    rng = random.Random(20261109)
    bootstrap = sorted(statistics.median(pairs[rng.randrange(len(pairs))] for _ in pairs)
                       for _ in range(10000))
    return {'paired_median_ratio': statistics.median(pairs),
            'ratio_of_medians': statistics.median(trial) / statistics.median(reference),
            'paired_bootstrap_95_interval': [bootstrap[249], bootstrap[9749]],
            'bootstrap_resamples': 10000, 'pairing': 'same interleaved repetition index'}


def work(sample):
    guards = sample.get('parallel_guards') or {}
    batches = sample.get('completion_batches') or {}
    a = guards.get('worker_candidates', [])
    b = batches.get('worker_tasks', [])
    workers = max(len(a), len(b))
    loads = [(a[i] if i < len(a) else 0) + (b[i] if i < len(b) else 0) for i in range(workers)]
    return {'configured_workers': guards.get('workers', 0),
            'workers_with_recorded_work': sum(value > 0 for value in loads),
            'worker_candidate_counts': a, 'worker_task_counts': b,
            'parallel_guard_stats': guards.get('stats'), 'completion_batch_stats': batches.get('stats'),
            'overlap': batches.get('overlap'),
            'source_waits_and_commits': (sample.get('scoped_executor') or {}).get('stats'),
            'port_completion': (sample.get('port_completion') or {}).get('stats')}


def collect(root, output):
    samples = json.loads((root / 'samples.json').read_text())
    assert 'failure' not in samples
    assert samples.get('finished_at_utc') and samples['repeat'] > 0
    lanes = samples['lanes']
    summary = {'scope': samples['scope'], 'repeat': samples['repeat'], 'warmups': samples['warmups'],
               'started_at_utc': samples['started_at_utc'], 'finished_at_utc': samples['finished_at_utc'],
               'semantics': samples['semantic_reference'], 'lanes': {}, 'comparisons': {},
               'limits': 'Guard reads run on workers; matching, effect commits and publication retain serial ownership. Worker counters demonstrate executed work, not CPU utilization. Whole-process time includes load, setup, inference, export, reporting and teardown. Small-sample bootstrap intervals are not cross-machine guarantees.'}
    for name, lane in lanes.items():
        rows = sorted(lane['samples'], key=lambda s: s['iteration'])
        assert [row['iteration'] for row in rows] == list(range(samples['repeat']))
        for row in rows:
            assert all(row[key] == value for key, value in samples['semantic_reference'].items())
        timing = {key: distribution([row[key] for row in rows]) for key in
                  ('inference_seconds', 'process_wall_seconds', 'peak_rss_through_inference_bytes')
                  if all(key in row for row in rows)}
        stage_names = rows[0]['phases'].keys()
        phases = {key: distribution([row['phases'][key] for row in rows]) for key in stage_names}
        details = [work(row) for row in rows]
        summary['lanes'][name] = {'args': lane['args'], 'runtime_sha256': lane['runtime_sha256'],
                                 'program_file_sha256': lane['program_file_sha256'],
                                 'timing': timing, 'source_run_phase_seconds': phases,
                                 'minimum_workers_with_recorded_work': min(x['workers_with_recorded_work'] for x in details),
                                 'first_sample_work': details[0],
                                 'first_sample_counters': {key: rows[0].get(key) for key in
                                     ('stats', 'key_lookup_calls', 'cell_ownership_stats', 'stable_ports_stats')},
                                 'samples': [{key: row.get(key) for key in ('iteration', 'inference_seconds',
                                     'process_wall_seconds', 'process_user_seconds', 'process_system_seconds')}
                                     for row in rows]}
    for baseline in ('fast_archived', 'fast_before', 'fast_current', 'local_before', 'local_serial', 'pure_serial'):
        if baseline not in lanes:
            continue
        reference = sorted(lanes[baseline]['samples'], key=lambda s: s['iteration'])
        summary['comparisons'][baseline] = {}
        for name, lane in lanes.items():
            trial = sorted(lane['samples'], key=lambda s: s['iteration'])
            summary['comparisons'][baseline][name] = {
                key: paired_ratio([row[key] for row in reference], [row[key] for row in trial])
                for key in ('inference_seconds', 'process_wall_seconds')}
    output.write_text(json.dumps(summary, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    collect(args.root, args.output)

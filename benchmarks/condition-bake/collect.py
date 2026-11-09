#!/usr/bin/env python3
"""Summarize paired single-thread condition-compiler pilots without retiming."""
import argparse
import json
from pathlib import Path
import runpy
import statistics

common = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-parallel' / 'collect.py'))


def collect(root, output, reference):
    raw = json.loads((root / 'samples.json').read_text())
    assert raw.get('finished_at_utc') and 'failure' not in raw
    assert 'blocking waitpid' in raw['process_wait']
    result = {key: raw[key] for key in ('scope', 'repeat', 'warmups', 'started_at_utc',
                                       'finished_at_utc', 'semantic_reference', 'process_wait', 'execution_order')}
    result['reference'] = reference
    result['lanes'] = {}
    result['comparisons'] = {}
    fast_names = sorted(set(raw['lanes']) & {'fast_archive', 'archived-fast', 'fast_archived'})
    result['concurrent_fast_reference_lanes'] = fast_names
    reference_note = ('An archived-fast reference was included in this same campaign: '
                      + ', '.join(fast_names) + '. ') if fast_names else (
                      'No archived-fast reference was rerun concurrently with these lanes. ')
    result['limits'] = ('A bounded single-thread pilot; small-sample intervals are descriptive. '
        + reference_note + 'Counter reductions alone do not establish a speedup; '
        'use measured inference and whole-process time.')
    for name, lane in raw['lanes'].items():
        rows = sorted(lane['samples'], key=lambda row: row['iteration'])
        assert [row['iteration'] for row in rows] == list(range(raw['repeat']))
        assert all(all(row[k] == v for k, v in raw['semantic_reference'].items()) for row in rows)
        timing = {key: common['distribution']([row[key] for row in rows]) for key in
                  ('inference_seconds', 'process_wall_seconds', 'load_seconds', 'setup_seconds',
                   'export_seconds', 'peak_rss_through_inference_bytes')
                  if all(key in row for row in rows)}
        counter_groups = ('key_lookup_calls', 'cell_ownership_stats', 'stable_ports_stats',
                          'birth_absence_directory', 'stats')
        counters = {key: rows[0].get(key) for key in counter_groups}
        for row in [*lane['warmup_samples'], *rows]:
            for key, expected in counters.items():
                assert row.get(key) == expected, (name, row['iteration'], key, 'counter mismatch')
        result['lanes'][name] = {key: lane[key] for key in ('args', 'runtime_sha256', 'program_file_sha256')}
        result['lanes'][name].update(timing=timing, counters=counters,
            deterministic_counter_check={'groups': counter_groups, 'measured_samples': len(rows),
                'warmup_samples': len(lane['warmup_samples']), 'all_equal': True},
            phases={key: statistics.median(row['phases'][key] for row in rows) for key in rows[0]['phases']},
            samples=[{key: row[key] for key in ('iteration', 'inference_seconds', 'process_wall_seconds',
                'process_user_seconds', 'process_system_seconds')} for row in rows])
        if name != reference:
            before = sorted(raw['lanes'][reference]['samples'], key=lambda row: row['iteration'])
            result['comparisons'][name] = {key: common['paired_ratio'](
                [row[key] for row in before], [row[key] for row in rows])
                for key in ('inference_seconds', 'process_wall_seconds')}
    output.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--reference', default='baseline')
    args = parser.parse_args()
    collect(args.root, args.output, args.reference)

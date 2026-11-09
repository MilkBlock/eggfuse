#!/usr/bin/env python3
"""Collect frozen witness/prefix measurements, retaining every sample."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import statistics

HERE = Path(__file__).parent
BASE_COLLECT = runpy.run_path(str(HERE.parent / 'condition-bake' / 'collect.py'))['collect']
EXTRA_GROUPS = runpy.run_path(str(HERE / 'measure.py'))['GROUPS']


def deterministic(value):
    if isinstance(value, dict):
        return {key: deterministic(child) for key, child in value.items()
                if not key.endswith(('_seconds', '_ns'))}
    if isinstance(value, list):
        return [deterministic(child) for child in value]
    return value


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def collect(raw_root, output):
    metadata = json.loads((output / 'metadata.json').read_text())
    for name, expected in metadata['source_manifest'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == expected, ('changed source', name)
    phases = {'scope': 'All paired samples retained; mean phase differences add to mean wall difference, separate medians need not.',
              'cases': {}}
    for workload in ('sum-bits', 'raytrace'):
        source = raw_root / workload
        raw = json.loads((source / 'samples.json').read_text())
        BASE_COLLECT(source, output / f'{workload}.json', 'baseline')
        result = json.loads((output / f'{workload}.json').read_text())
        case = {'lanes': {}, 'paired_mean_decomposition': {}}
        for label, lane in raw['lanes'].items():
            target = result['lanes'][label]
            rows = sorted(lane['samples'], key=lambda row: row['iteration'])
            counter_groups = [key for key in EXTRA_GROUPS if key.endswith('_stats')]
            counters = {key: deterministic(rows[0][key]) for key in counter_groups}
            for row in [*lane['warmup_samples'], *rows]:
                for key, expected in counters.items():
                    assert deterministic(row[key]) == expected, (workload, label, row['iteration'], key)
                assert row['allocations'] is None and row['setup_allocations'] is None
            target['extended_counters'] = counters
            target['extended_deterministic_counter_check'] = {
                'groups': counter_groups, 'all_equal': True, 'includes_warmup': True,
                'excluded_fields': 'keys ending _seconds or _ns; raw samples retain them',
            }
            target['metric_presence'] = rows[0]['metric_presence']
            target['allocation_status'] = rows[0]['allocation_status']
            target['all_samples_file'] = f'{workload}-samples.json'
            case['lanes'][label] = {
                'phase_medians': {key: value['median'] for key, value in target['timing'].items() if key.endswith('_seconds')},
                'samples': target['samples'],
            }
        for name in ('candidate', 'fast_archived'):
            before = raw['lanes']['baseline']['samples']
            after = raw['lanes'][name]['samples']
            components = ['load_seconds', 'setup_seconds', 'inference_seconds', 'export_seconds']
            components += (['report_seconds', 'process_after_report_residual_seconds']
                           if all('report_seconds' in row for row in [*before, *after])
                           else ['process_unattributed_seconds'])
            if all(key in row for row in [*before, *after] for key in components):
                delta = {key: statistics.mean(b[key] - a[key] for a, b in zip(before, after)) for key in components}
                wall = statistics.mean(b['process_wall_seconds'] - a['process_wall_seconds'] for a, b in zip(before, after))
                assert abs(sum(delta.values()) - wall) < 1e-9
                case['paired_mean_decomposition'][f'{name}_minus_baseline'] = {
                    'unit': 'seconds', 'components': delta, 'whole_process_delta': wall}
        phases['cases'][workload] = case
        save(output / f'{workload}.json', result)
        save(output / f'{workload}-samples.json', raw)
    save(output / 'phase-attribution.json', phases)
    metadata['source_unchanged_during_normal_timing'] = True
    metadata['finished_at_utc'] = raw['finished_at_utc']
    save(output / 'metadata.json', metadata)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('raw_root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    collect(args.raw_root, args.output)

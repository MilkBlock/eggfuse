#!/usr/bin/env python3
"""Collect the four-lane query-class pilot without executing a workload."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import statistics

summarize = runpy.run_path(str(Path(__file__).parents[1] / 'condition-bake' / 'collect.py'))['collect']


def collect(raw_root, output, ablation='receipts'):
    metadata = json.loads((output / 'metadata.json').read_text())
    for name, expected in metadata['source_manifest'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == expected, ('changed source', name)
    attribution = {'scope': 'Paired time accounting; no samples removed. Mean phase differences are additive; separate phase medians are not.', 'cases': {}}
    for workload in ('sum-bits', 'raytrace'):
        raw = raw_root / workload
        summarize(raw, output / f'{workload}.json', 'baseline')
        summarize(raw, output / f'{workload}-vs-{ablation}.json', ablation)
        report = json.loads((output / f'{workload}.json').read_text())
        case = {'lanes': {name: {'phase_medians': {key: value['median'] for key, value in lane['timing'].items() if key.endswith('_seconds')},
                                 'samples': lane['samples']} for name, lane in report['lanes'].items()},
                'paired_mean_decomposition': {}}
        for reference in ('baseline', ablation):
            before = report['lanes'][reference]['samples']
            for name, lane in report['lanes'].items():
                if name == reference:
                    continue
                after = lane['samples']
                components = ['load_seconds', 'setup_seconds', 'inference_seconds', 'export_seconds']
                if all('report_seconds' in row for row in [*before, *after]):
                    components += ['report_seconds', 'process_after_report_residual_seconds']
                else:
                    components += ['process_unattributed_seconds']
                if not all(key in row for row in [*before, *after] for key in components):
                    continue  # Old fast executable omits load; do not invent it.
                delta = {key: statistics.mean(b[key] - a[key] for a, b in zip(before, after)) for key in components}
                wall = statistics.mean(b['process_wall_seconds'] - a['process_wall_seconds'] for a, b in zip(before, after))
                assert abs(sum(delta.values()) - wall) < 1e-9
                case['paired_mean_decomposition'][f'{name}_minus_{reference}'] = {'unit': 'seconds', 'components': delta, 'whole_process_delta': wall}
        attribution['cases'][workload] = case
    (output / 'phase-attribution.json').write_text(json.dumps(attribution, indent=2) + '\n')
    metadata['source_unchanged_during_normal_timing'] = True
    metadata['finished_at_utc'] = json.loads((raw_root / 'raytrace' / 'samples.json').read_text())['finished_at_utc']
    (output / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('raw_root', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--ablation', default='receipts')
    args = parser.parse_args()
    collect(args.raw_root, args.output, args.ablation)

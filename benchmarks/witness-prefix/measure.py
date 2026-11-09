#!/usr/bin/env python3
"""Extend the frozen process harness with this experiment's report groups."""
import argparse
import json
from pathlib import Path
import runpy

BASE = Path(__file__).parents[1] / 'raytrace-parallel' / 'measure.py'
GROUPS = {
    'stage_spine_stats': ('stage_spine', 'stats'),
    'entry_schedule_stats': ('entry_schedule', 'stats'),
    'register_prefix_stats': ('stats', 'register_prefix'),
    'multi_stage_stats': ('multi_stage', 'stats'),
    'free_join_stats': ('free_join',),
    'known_results_stats': ('known_results',),
    'storage': ('storage',),
    'allocations': ('allocations',),
    'setup_allocations': ('setup_allocations',),
}


def extra_groups(report):
    groups = {}
    for label, path in GROUPS.items():
        value = report
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        groups[label] = value
    groups['metric_presence'] = {key: value is not None for key, value in groups.items()}
    groups['allocation_status'] = ('collected_diagnostic_build' if groups['allocations'] is not None
                                   else 'not_collected_normal_build; absence is not zero allocations')
    return groups


def measure(spec, output, repeat, warmups, timeout):
    base = runpy.run_path(str(BASE))
    original_save = base['save']

    def save_with_extra_groups(path, result):
        # The old harness calls save after waiting, reading the report and
        # recording wall time, but before deleting the report. Capture extra
        # groups here without altering its timing boundary, shuffle or checks.
        for index, lane in enumerate(result['lanes'].values()):
            for row in [*lane['warmup_samples'], *lane['samples']]:
                if 'metric_presence' in row:
                    continue
                directory = output / f'run-{row["iteration"] + warmups:04d}-{index:04d}'
                report = json.loads((directory / 'report.json').read_text())
                row.update(extra_groups(report))
                assert row['allocations'] is None and row['setup_allocations'] is None, (
                    'This campaign requires ordinary timing binaries, not allocator builds')
        result['report_extension'] = {
            'groups': GROUPS,
            'scope': 'Extra report parsing occurs after measured child termination; frozen base harness is unchanged',
            'allocation_policy': 'Normal timing records missing allocation metrics explicitly; allocation diagnostics are separate',
        }
        original_save(path, result)

    base['measure'].__globals__['save'] = save_with_extra_groups
    base['measure'](spec, output, repeat, warmups, timeout)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spec', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--repeat', type=int, default=3)
    parser.add_argument('--warmups', type=int, default=1)
    parser.add_argument('--timeout', type=float, default=180)
    args = parser.parse_args()
    assert args.repeat > 0 and args.warmups >= 0
    measure(json.loads(args.spec.read_text()), args.output, args.repeat, args.warmups, args.timeout)

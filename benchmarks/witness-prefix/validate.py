#!/usr/bin/env python3
"""Summarize normal timing gates and semantic evidence without retiming."""
import argparse
import json
from pathlib import Path


def validate(root):
    summary = {
        'scope': 'standalone Cell CPU; frozen normal binaries, three paired single-thread repetitions per workload',
        'two_workload_inference_and_process_gate_passed': True,
        'historical_fast_beaten': True,
        'gate_rule': 'All paired candidate inference/process times below baseline on both workloads; three pairs remain a bounded pilot, not robust general performance proof.',
        'allocation_validation': 'not collected in normal timing; diagnostic audit handled separately',
        'cases': {},
    }
    for name in ('sum-bits', 'raytrace'):
        report = json.loads((root / f'{name}.json').read_text())
        raw = json.loads((root / f'{name}-samples.json').read_text())
        before, after, fast = (report['lanes'][label] for label in ('baseline', 'candidate', 'fast_archived'))
        faster = {key: sum(a[key] < b[key] for a, b in zip(
            raw['lanes']['candidate']['samples'], raw['lanes']['baseline']['samples']))
            for key in ('inference_seconds', 'process_wall_seconds')}
        relative_fast = {key: after['timing'][key]['median'] / fast['timing'][key]['median']
                         for key in faster}
        summary['two_workload_inference_and_process_gate_passed'] &= all(n == raw['repeat'] for n in faster.values())
        summary['historical_fast_beaten'] &= all(ratio < 1 for ratio in relative_fast.values())
        summary['cases'][name] = {
            'raw_state_and_ordered_run_sha_equal': all(
                all(row[key] == value for key, value in raw['semantic_reference'].items())
                for lane in raw['lanes'].values() for row in [*lane['warmup_samples'], *lane['samples']]),
            'semantic_reference': report['semantic_reference'],
            'all_counters_deterministic_including_warmup': all(
                lane['deterministic_counter_check']['all_equal'] and lane['extended_deterministic_counter_check']['all_equal']
                for lane in report['lanes'].values()),
            'candidate_pairs_faster': faster,
            'key_lookup_calls': {'baseline': before['counters']['key_lookup_calls'], 'candidate': after['counters']['key_lookup_calls']},
            'prefix_key_reads_avoided': after['extended_counters']['register_prefix_stats']['key_reads_avoided'],
            'spine_local_witness_hits': after['extended_counters']['stage_spine_stats']['local_witness_hits'],
            'candidate_over_fast_median_ratio': relative_fast,
        }
    (root / 'validation.json').write_text(json.dumps(summary, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    validate(parser.parse_args().root)

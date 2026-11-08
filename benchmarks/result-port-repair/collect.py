#!/usr/bin/env python3
"""Keep every timing sample; deduplicate counters only after exact comparison.

The input is leaf-completion/measure.py's samples.json. The output stores one
invariants object per lane, including all graph, Spine and result-port counters.
"""
import argparse
import json
from pathlib import Path


def collect(source):
    for lanes in source['cases'].values():
        for row in lanes.values():
            assert len(row['samples']) == source['repeat']
            assert 'median_inference_seconds' in row
            reference = None
            for sample in [row['warmup'], *row['samples']]:
                fixed = {k: sample.pop(k) for k in ('stats', 'repair_ports', 'state_file_sha256', 'schedule_sha256')}
                for key in ('entry_schedule', 'publication', 'key_lookup_calls', 'fact_decode_calls', 'fact_decode_ports', 'repair_cells'):
                    if key in sample:
                        fixed[key] = sample.pop(key)
                fixed['stage_spine'] = {k: v for k, v in sample['stage_spine'].items() if not k.endswith('_seconds')}
                sample['stage_spine'] = {k: v for k, v in sample['stage_spine'].items() if k.endswith('_seconds')}
                if reference is None:
                    reference = fixed
                assert fixed == reference, 'execution counters changed between samples'
            row['invariants'] = reference
    return source


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(collect(json.loads(args.input.read_text())), indent=2) + '\n')

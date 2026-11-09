#!/usr/bin/env python3
"""Retain ordered audit evidence without duplicating large static plans."""
import argparse
import hashlib
import json
from pathlib import Path


def compact(current, previous):
    out = {'scope': current['scope'], 'runtime_sha256': current['runtime_sha256'],
           'omitted': 'static plans and repeated inventory; original audit.py output is reproducible',
           'cases': {}}
    for case, data in current['cases'].items():
        reference = previous['cases'][case]['lanes']['local']['hashes']
        lanes = {}
        for lane, row in data['lanes'].items():
            for key, value in row['hashes'].items():
                if key != 'spine-shapes.json':
                    assert value == reference[key], (case, lane, key)
            keep = {key: row[key] for key in ('program_file_sha256', 'args', 'hashes', 'runs',
                    'stats', 'stage_spine', 'key_lookup_calls', 'entry_schedule', 'publication')}
            keep['prior_final_ordered_equal'] = True
            keep['cell_ownership_stats'] = row['cell_ownership']['stats']
            keep['stable_port_stats'] = row['stable_ports']['stats']
            keep['local_condition_stats'] = row['stable_ports']['local_conditions']['stats']
            keep['completion_batches'] = row['stable_ports']['completion_batches']
            lanes[lane] = keep
        out['cases'][case] = {'lanes': lanes}
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('current', type=Path)
    parser.add_argument('previous', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    current = json.loads(args.current.read_text())
    previous = json.loads(args.previous.read_text())
    result = compact(current, previous)
    result['input_sha256'] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in (args.current, args.previous)}
    args.output.write_text(json.dumps(result, indent=2) + '\n')

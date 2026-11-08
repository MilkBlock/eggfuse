#!/usr/bin/env python3
"""Check structural gates, then retain the single final application evaluation."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def barriers(value, keep=False):
    if isinstance(value, list):
        return [barriers(x, keep) for x in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key == 'barriers' and isinstance(item, list):
            stamp = hashlib.sha256(json.dumps(item, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            if keep and item:
                columns = list(item[0])
                result[key] = dict(sha256=stamp, columns=columns,
                                   rows=[[row[c] for c in columns] for row in item])
            else:
                result[key] = dict(sha256=stamp, count=len(item),
                                   first=item[0] if item else None,
                                   last=item[-1] if item else None)
        else:
            result[key] = barriers(item, keep)
    return result


def pretty(value, depth=0):
    """Keep numerical stage rows on one line; preserve normal object structure."""
    if isinstance(value, list):
        if all(not isinstance(x, (list, dict)) for x in value):
            return json.dumps(value)
        parts = [pretty(x, depth + 1) for x in value]
        ends = ('[', ']')
    elif isinstance(value, dict):
        if not value:
            return '{}'
        parts = [json.dumps(k) + ': ' + pretty(v, depth + 1) for k, v in value.items()]
        ends = ('{', '}')
    else:
        return json.dumps(value)
    return ends[0] + '\n' + ',\n'.join('  ' * (depth + 1) + x for x in parts) + '\n' + '  ' * depth + ends[1]


def collect(root, destination):
    base = Path(__file__).resolve().parents[1]
    compact = module('compact_evidence', base / 'local-unions/collect.py').compact
    timing = module('timing_evidence', base / 'result-port-repair/collect.py').collect
    audit = read(root / 'audit/results.json')
    gates = {'scope': 'standalone Cell CPU; structural counters are not timings', 'cases': {}}
    for name, case in audit['cases'].items():
        lane = case['lanes']['owned']
        report = lane['cell_ownership']
        stats, inv = report['stats'], report['inventory']
        assert report['enabled'] is True and report['pending_keys'] == 0
        assert stats['owned_live'] == inv['eligible_live_facts']
        assert inv['largest_owner'] <= report['plan']['plan']['max_continuation_facts']
        assert inv['internal_eq_ports'] > 0 and inv['cross_stage_live_facts'] > 0
        assert stats['cross_stage_continuations'] > 0
        assert report['barriers']
        gates['cases'][name] = {
            'inventory': inv, 'stats': stats, 'barriers': report['barriers'],
            'remaining_legacy_maintenance': lane['maintenance'],
            'baseline_legacy_maintenance': case['lanes']['control']['maintenance'],
            'source_publication_stats': lane['stage_spine'],
            'shared_entry_stats': lane['entry_schedule'],
            'full_eligible_body_coverage': True,
            'runtime_assertions': ['no owned fact in legacy dependencies',
                                   'all settled owned fields canonical',
                                   'every foreign equality port has an owner boundary',
                                   'boundary/live-body gauges match physical storage'],
        }
    def save(name, value, keep=False):
        (destination / name).write_text(pretty(compact(barriers(value, keep))) + '\n')
    save('audit.json', audit)
    save('monitor.json', gates, keep=True)
    for case in ['sum', 'raytrace']:
        save(f'timings-{case}.json', timing(read(root / f'timing-{case}/samples.json')))
    save('bake.json', {'scope': 'compiler only; no application inference',
                      'compiler_sha256': hashlib.sha256((root / 'compiler').read_bytes()).hexdigest(),
                      'cases': {case: read(root / f'baked-{case}/coverage.json')
                                for case in ['sum', 'raytrace']}})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('destination', type=Path)
    a = p.parse_args()
    collect(a.root, a.destination)

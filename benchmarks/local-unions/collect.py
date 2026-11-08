#!/usr/bin/env python3
"""Retain audits, operation deltas and all timing samples without repeated plans."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact(value):
    if isinstance(value, list):
        return [compact(x) for x in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key in ('by_template', 'by_table') and isinstance(item, list):
            result[key] = {str(i): x for i, x in enumerate(item)
                           if (any(x) if isinstance(x, list) else x)}
        elif key in ('plan', 'catalog') and isinstance(item, dict):
            result[key + '_summary'] = {
                'sha256': hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest(),
                'selected': item.get('selected'),
                'templates': len(item.get('templates', [])),
                'shapes': len(item.get('shapes', [])),
            }
        else:
            result[key] = compact(item)
    return result


def save(path, value):
    path.write_text(json.dumps(compact(value), indent=2) + '\n')


def collect(root, destination):
    save(destination / 'audit.json', read(root / 'audit/results.json'))
    credit = {'scope': 'standalone Cell CPU; equal-weight observed work, not latency',
              'compiler_sha256': digest(root / 'compiler'), 'cases': {}}
    for name, folder in [('sum-bits', 'learn-sum'), ('raytrace', 'learn-raytrace')]:
        directory = root / folder
        record = read(directory / 'credit.json')
        assert record['semantic_audit'] is True
        counters = record['work']['counters']
        assert all(x['before'] - x['after'] == x['saved'] for x in counters.values())
        net = sum(x['saved'] for x in counters.values())
        assert net == record['work']['net_saved_operations']
        assert record['accepted'] == (net > 0)
        program = read(directory / 'program.json')
        selected = program['local_union_cells']['selected']
        assert record['accepted'] or not selected
        credit['cases'][name] = dict(record, selected=selected,
                                    program_file_sha256=digest(directory / 'program.json'))
    save(destination / 'credit.json', credit)
    spec = importlib.util.spec_from_file_location(
        'timing_collector', Path(__file__).resolve().parents[1] / 'result-port-repair/collect.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ['sum', 'raytrace']:
        samples = module.collect(read(root / f'timing-{name}/samples.json'))
        save(destination / f'timings-{name}.json', samples)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    collect(args.root, args.destination)

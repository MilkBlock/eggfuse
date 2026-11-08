#!/usr/bin/env python3
"""Collect compact evidence; do not retain generated graph exports."""
import argparse
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(root, destination):
    audit = read(root / 'audit/results.json')
    for case in audit['cases'].values():
        for lane in case['lanes'].values():
            cells = lane['repair_cells']
            plan = cells.pop('catalog')
            cells['catalog_summary'] = {
                'shapes': len(plan['shapes']), 'selected': plan['selected'],
                'eligible_table_bindings': sum(x is not None for x in plan['tables']),
                'template_nodes': 5 * len(plan['shapes']),
                'catalog_sha256': hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest(),
            }
    (destination / 'audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    credit = {'scope': 'standalone Cell CPU; observed operations, not elapsed-time credit',
              'compiler_sha256': digest(root / 'compiler'), 'cases': {}}
    for name, folder in [('sum-bits', 'learn-sum'), ('raytrace', 'learn-raytrace')]:
        directory = root / folder
        history = read(directory / 'rounds.json')
        for round_ in history:
            for trial in round_['trials']:
                assert trial['semantic_audit'] is True
                counters = trial['work']['counters']
                assert all(x['before'] - x['after'] == x['saved'] for x in counters.values())
                assert sum(x['saved'] for x in counters.values()) == trial['work']['net_saved_operations']
            if round_['net_saved_operations'] > 0:
                assert any(t['selected'] == round_['selected'] and
                           t['work']['net_saved_operations'] == round_['net_saved_operations']
                           for t in round_['trials'])
        registry = read(directory / 'cell-egraph.json')
        final = read(directory / 'program.json')
        credit['cases'][name] = {
            'program_file_sha256': digest(directory / 'program.json'),
            'selected_shapes': final['repair_cells']['selected'],
            'source_units': registry['source_units'], 'repair_units': registry['repair_units'],
            'cell_egraph_file_sha256': digest(directory / 'cell-egraph.json'),
            'audit': read(directory / 'audit.json'), 'rounds': history,
        }
    (destination / 'credit.json').write_text(json.dumps(credit, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    collect(args.root, args.destination)

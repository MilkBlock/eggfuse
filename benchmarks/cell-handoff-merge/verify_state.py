#!/usr/bin/env python3
"""Verify saved selected/materialized v2 runs against the pre-merge execution."""
import argparse
import hashlib
import json
from pathlib import Path

RUN_FIELDS = ['ordinal', 'ruleset', 'path', 'iterations', 'epoch',
              'logical_matches', 'executed_bindings', 'changed']
WORK_FIELDS = ['history_inherited_slots', 'history_inherited_reads',
               'history_inheritance_marks', 'history_capture_reads', 'history_slots_written']


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stamp(directory):
    return (sha(directory / 'state.json'),
            [[r[k] for k in RUN_FIELDS] for r in read(directory / 'report.json')['steps']])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('original_program', type=Path)
    args = parser.parse_args()
    root = args.root
    baseline = stamp(root / 'checks/sum-baseline')
    original = read(args.original_program)
    original.pop('sha256')
    original['iterative_bake'].pop('state_plan', None)
    result = {'scope': 'standalone Cell CPU; selected v2 state plan versus materialized control '
                      'and pre-merge runtime; no timing', 'exact_final_graph_and_runs': True,
              'runs': len(baseline[1]), 'state_sha256': baseline[0], 'lanes': {}}
    for lane in ['state', 'materialized']:
        directory = root / f'sum-{lane}'
        assert stamp(directory) == baseline
        program_path = root / f'sum-{lane}-program.json'
        program = read(program_path)
        program.pop('sha256')
        program['iterative_bake'].pop('state_plan')
        assert program == original
        stats = read(directory / 'report.json')['stage_spine']['stats']
        result['lanes'][lane] = {'program_sha256': sha(program_path),
                                'stats': {k: stats[k] for k in WORK_FIELDS}}
    acceptance = read(root / 'state-acceptance.json')
    assert acceptance['status'] == 'pass'
    result['semantic_acceptance'] = acceptance['status']
    result['acceptance_sha256'] = sha(root / 'state-acceptance.json')
    result['handoff'] = {lane: {'schema': read(root / f'{lane}-handoff.json')['schema'],
        'sha256': sha(root / f'{lane}-handoff.json'),
        'bytes': (root / f'{lane}-handoff.json').stat().st_size} for lane in ['sum', 'ray']}
    (root / 'state-check.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

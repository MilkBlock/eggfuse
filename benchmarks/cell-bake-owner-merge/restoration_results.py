#!/usr/bin/env python3
"""Summarize frozen-catalog restoration replays; never infer a speedup."""
import hashlib
import json
import sys
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def collect(replays, catalogs):
    rows = []
    for case in ('fact', 'loopfact', 'sum-bits', 'dot-product'):
        replay = read(replays / (case + '.json'))
        saved = read(catalogs / case / 'catalog-observation.json')
        program_path = catalogs / case / 'candidate.json'
        program = read(program_path)
        if replay['program_sha256'] != program['sha256']:
            raise ValueError(f'{case}: different program')
        if replay['runs'] != saved['runs']:
            raise ValueError(f'{case}: different Run count')
        if replay['final_state_sha256'] != saved['final_state']:
            raise ValueError(f'{case}: final-state mismatch')
        if replay['mode'] != 'inherited-owners':
            raise ValueError(f'{case}: wrong storage mode')
        fields = dict(replay['graph_fields'])
        graph = replay['graph_owned_teardown_bytes']
        if sum(fields.values()) + replay['graph_unlisted_teardown_bytes'] != graph:
            raise ValueError(f'{case}: inconsistent teardown accounting')
        owner = replay['source_storage']['completed_owners']
        maintenance = sum(fields.get(k, 0) for k in (
            'stable_ports', 'ownership.components', 'ownership.boundaries',
            'ownership.frames'))
        rows.append(dict(
            case=case, program=program['sha256'],
            program_file_sha256=hashlib.sha256(program_path.read_bytes()).hexdigest(),
            runs=replay['runs'], final_state=replay['final_state_sha256'],
            saved_final_state_equal=True, graph_owned_bytes=graph,
            restoration=owner['restoration'],
            completed_frames=owner['completed_frames'],
            cross_stage_owners=owner['cross_stage_owners'],
            old_slots_moved=replay['completion_work']['shared_owner_slot_entries_moved'],
            old_facts_moved=replay['completion_work']['shared_owner_fact_entries_moved'],
            cell_bytes=fields['cells'], routing_and_stable_storage_bytes=maintenance,
            routing_and_stable_storage_fraction=maintenance / graph,
            barrier_history_bytes=fields.get('ownership.barriers', 0),
            graph_fields=fields))
    return dict(scope='Standalone Cell CPU; opt-in completed owners; no native equivalence or timing claim',
                validation='Frozen program identity, Run count and saved final graph digest; not per-Run acceptance',
                cases=rows)


if __name__ == '__main__':
    result = collect(Path(sys.argv[1]), Path(sys.argv[2]))
    Path(sys.argv[3]).write_text(json.dumps(result, indent=2) + '\n')
    for row in result['cases']:
        print(row['case'], row['restoration'],
              'routing fraction', round(row['routing_and_stable_storage_fraction'], 3))

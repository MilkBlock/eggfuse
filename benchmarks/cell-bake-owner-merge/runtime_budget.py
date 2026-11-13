#!/usr/bin/env python3
"""Account frozen full-Graph heaps; hypothetical removal is not legal savings."""
import hashlib
import json
import sys
from pathlib import Path

CASES = ('fact', 'loopfact', 'sum-bits', 'dot-product')
GROUPS = {
    'instances': {'cells'},
    'composition_addressing': {'ownership.components', 'ownership.frames', 'ownership.live_facts'},
    'boundary_routes': {'ownership.boundaries'},
    'stable_fields': {'stable_ports'},
    'functions_and_writers': {'functions', 'writer_dir', 'function_keys'},
}

def source_lifetimes(data):
    """Separate source-storage lifetime from the shared wiring's lifetime."""
    frames = data['source_storage']['fact_lifecycle']['frames']
    sources = {frame['cell']: frame for frame in frames}
    assert len(sources) == len(frames), 'duplicate source identity'
    owner = data['source_storage']['completed_owners']
    completed = sum(frame['completed_storage'] for frame in frames)
    assert completed == owner['completed_frames'], 'incomplete completed source inventory'
    assert len(frames) - completed == owner['source_records'], 'incomplete ordinary source inventory'
    composition = {}
    for component in data['ownership_storage']['components']:
        for ordinal, cell in enumerate(component['frames']):
            assert cell not in composition, 'duplicate composition identity'
            composition[cell] = (component['id'], ordinal)
    both = sources.keys() & composition.keys()
    wiring_only = composition.keys() - sources.keys()
    storage_only = sources.keys() - composition.keys()
    # These are distinct state obligations, not removable duplicate records.
    return {
        'storage_and_wiring': len(both),
        'wiring_without_source_storage': len(wiring_only),
        'storage_without_wiring': len(storage_only),
        'storage_without_wiring_with_external_retainers': sum(
            sources[cell]['retainers'] > 0 for cell in storage_only),
        'storage_and_wiring_completed': sum(sources[cell]['completed'] for cell in both),
        'storage_and_wiring_with_external_retainers': sum(
            sources[cell]['retainers'] > 0 for cell in both),
        'completed_storage_and_wiring': sum(
            sources[cell]['completed_storage'] for cell in both),
        'source_position_array_bytes': data['source_storage']['cell_positions_bytes'],
        'source_position_array_fraction_of_graph': (
            data['source_storage']['cell_positions_bytes'] / data['graph_owned_teardown_bytes']),
    }


def analyze(path):
    raw = path.read_bytes()
    data = json.loads(raw)
    fields = dict(data['graph_fields'])
    assert len(fields) == len(data['graph_fields']), 'duplicate accounting field'
    total = data['graph_owned_teardown_bytes']
    unlisted = data['graph_unlisted_teardown_bytes']
    assert sum(fields.values()) + unlisted == total, 'incomplete heap accounting'
    assert all(value >= 0 for value in fields.values()) and unlisted >= 0
    groups = {name: sum(fields[field] for field in members) for name, members in GROUPS.items()}
    groups['other_graph_state'] = total - sum(groups.values())
    assert sum(groups.values()) == total
    target = total * 3 // 10
    # Stronger than any legal implementation: even remove all source instances.
    # This is an upper bound on that avenue, never a proposed representation.
    remainder = total - groups['instances']
    return {
        'input_sha256': hashlib.sha256(raw).hexdigest(),
        'program_sha256': data['program_sha256'],
        'final_state_sha256': data['final_state_sha256'],
        'graph_bytes': total,
        'groups': groups,
        'source_lifetimes': source_lifetimes(data),
        'group_fraction': {k: v / total for k, v in groups.items()},
        'thirty_percent_of_this_snapshot_bytes': target,
        'hypothetical_zero_instance_remainder_bytes': remainder,
        'additional_bytes_outside_instances_required': max(0, remainder - target),
        'observed_fact_records': sum(len(f['facts']) for f in data['source_storage']['fact_lifecycle']['frames']),
    }

if __name__ == '__main__':
    root = Path(sys.argv[1])
    rows = {case: analyze(root / (case + '-pooled.json')) for case in CASES}
    result = {
        'scope': 'Offline accounting of existing standalone Cell runtime snapshots; no timing or new execution',
        'target_note': '30% here is relative to each pooled snapshot, not a replacement for the original baseline target.',
        'limitations': [
            'Groups include useful live values and capacities; none is proved removable.',
            'Graph self-owned teardown excludes retained Program, allocator metadata and process RSS.',
            'No counter is a rule-skip proof; source identities may have live external users.',
        ],
        'cases': rows,
    }
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + '\n')
    for case, row in rows.items():
        print(case, row['graph_bytes'], row['groups'], row['additional_bytes_outside_instances_required'])

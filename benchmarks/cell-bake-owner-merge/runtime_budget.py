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

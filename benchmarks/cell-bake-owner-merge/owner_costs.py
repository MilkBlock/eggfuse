#!/usr/bin/env python3
"""Audit saved runtime owner costs without rerunning or training workloads."""
import hashlib
import json
import sys
from pathlib import Path


def collect(root):
    rows = []
    for case in ('fact', 'loopfact', 'sum-bits', 'dot-product'):
        path = root / f'{case}-multi.json'
        data = json.loads(path.read_text())
        source = data['source_storage']
        owner = source['completed_owners']
        fields = dict(data['graph_fields'])
        total = data['graph_owned_teardown_bytes']
        if sum(fields.values()) + data['graph_unlisted_teardown_bytes'] != total:
            raise ValueError(f'{case}: inconsistent heap accounting')
        widths = {int(k): v for k, v in owner['owner_widths'].items()}
        if sum(k * v for k, v in widths.items()) != owner['completed_frames']:
            raise ValueError(f'{case}: inconsistent frame counts')
        slots = owner['stored_slot_entries'] - owner['live_slot_entries']
        facts = owner['stored_fact_entries'] - owner['live_fact_entries']
        if slots != owner['retired_slot_entries'] or min(slots, facts) < 0:
            raise ValueError(f'{case}: inconsistent retired entries')
        restoration = owner['restoration']
        work = data['completion_work']
        routing = sum(fields[k] for k in ('ownership.components', 'ownership.frames',
                                          'ownership.boundaries', 'stable_ports'))
        rows.append(dict(case=case, input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            program_sha256=data['program_sha256'], graph_owned_bytes=total,
            restoration=restoration, max_owner_frames=max(widths, default=0),
            retired_slot_entries=slots, retired_fact_entries=facts,
            old_slots_moved=work['shared_owner_slot_entries_moved'],
            old_facts_moved=work['shared_owner_fact_entries_moved'],
            segment_extensions=work['shared_owner_segment_extensions'],
            routing_bytes=routing, routing_fraction=routing / total,
            completed_owner_records_bytes=source['completed_owner_records_bytes'],
            cell_records_bytes=source['cell_records_bytes']))
    return dict(scope='Saved standalone Cell CPU snapshots; no new execution or timing measurement',
        limitations=['Restoration causes do not identify the triggering union.',
                     'Retired entry counts do not measure retained bytes or peak lifetime.',
                     'Routing bytes are not all redundant; old-prefix moves are cumulative work.',
                     'Owner record bytes include capacities; not all are removable.'], cases=rows)


if __name__ == '__main__':
    result = collect(Path(sys.argv[1]))
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + '\n')
    for row in result['cases']:
        print(row['case'], 'restore', row['restoration']['capacity_bytes'],
              'old moves', row['old_slots_moved'] + row['old_facts_moved'],
              'routing', round(100 * row['routing_fraction'], 1))

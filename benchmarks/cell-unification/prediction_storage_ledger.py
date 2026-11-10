#!/usr/bin/env python3
"""Audit nonoverlapping retained bytes; estimate table payloads, never latency."""
import argparse
import json
from pathlib import Path
from check_links import load, sha


def total(data, keys):
    return sum(data[k] for k in keys)


def audit(catalog, completion, program):
    digest = program['sha256']
    assert catalog['program'] == completion['program'] == digest
    assert completion['plan']['source'] == digest
    captures = catalog['capture_storage']
    transitions = catalog['transition_storage']
    programs = catalog['completion_storage']
    assert captures['states'] == transitions['states'] == programs['states'] == len(catalog['contracts'])
    node_bytes = captures['node_array_bytes']
    assert node_bytes == transitions['node_array_bytes'] == programs['node_array_bytes']
    core = {
        'catalog_paths': total(catalog['storage'], ('unit_array_bytes', 'path_payload_bytes', 'lookup_key_bytes', 'lookup_payload_bytes')),
        'switch_dispatch': total(catalog['dispatch'], ('row_directory_bytes', 'rule_slot_bytes', 'root_slot_bytes', 'duplicate_lookup_entry_bytes')),
        'export_interfaces': total(catalog['export_storage'], ('directory_bytes', 'slot_bytes')),
        'state_array_once': node_bytes,
        'capture_programs': total(captures, ('capture_payload_bytes', 'capture_owner_bytes')),
        'transition_programs': total(transitions, ('transition_payload_bytes', 'transition_owner_bytes')),
        'completion_programs': total(programs, ('program_owner_bytes', 'read_payload_bytes')),
    }
    plan = completion['plan']
    owners = plan['completion_reads'] + list(plan['query_demands'].values())
    owners += [s['tables'] for s in plan['rulesets'].values()]
    owners += [r[k] for r in plan['rule_demands'] for k in ('query', 'rhs', 'accesses')]
    census = completion['table_lists']
    tables = len(plan['completion_reads'])
    for row in owners:
        assert row == sorted(set(row)), 'set encoding requires sorted unique table IDs'
        assert all(isinstance(t, int) and 0 <= t < tables for t in row)
    unique = set(map(tuple, owners))
    assert len(owners) == census['lists'] and len(unique) == census['unique_lists']
    assert sum(map(len, owners)) == census['logical_values']
    word, remainder = divmod(census['handles_bytes'], 2*len(owners))
    assert remainder == 0 and word in (4, 8)
    payload = sum(len(row)*word for row in unique)
    assert payload + len(unique)*2*word == census['shared_payload_and_rc_bytes']
    # The old rule-only demand census is a subset, not another allocation group.
    demands = {tuple(r[k]) for r in plan['rule_demands'] for k in ('query', 'rhs', 'accesses')}
    assert demands <= unique
    assert len(demands) == completion['storage']['unique_lists']
    assert sum(len(row)*word+2*word for row in demands) == completion['storage']['shared_payload_and_rc_bytes']
    extra = {
        'all_table_lists_once': total(census, ('shared_payload_and_rc_bytes', 'handles_bytes')),
        'repair_matrices': total(completion['matrices'], ('shared_payload_and_rc_bytes', 'directory_bytes')),
        'scope_masks': total(completion['scope_masks'], ('packed_payload_bytes', 'descriptor_bytes')),
    }
    bitmap_bytes = ((tables+63)//64)*8
    dense = [row for row in unique if len(row)*word > bitmap_bytes]
    estimate = {
        'table_universe': tables, 'word_bytes': word,
        'unique_lists': len(unique), 'dense_candidate_lists': len(dense),
        'current_unique_id_payload_bytes': payload,
        'dense_candidate_current_payload_bytes': sum(len(row)*word for row in dense),
        'bitmap_bytes_per_dense_list': bitmap_bytes,
        'hybrid_unique_payload_bytes': sum(min(len(row)*word, bitmap_bytes) for row in unique),
        'scope': 'Payload estimate only, not implemented or measured retained storage. Excludes variant descriptors, ownership, interning and iteration costs; no speed prediction.',
    }
    estimate['potential_payload_bytes_saved'] = payload-estimate['hybrid_unique_payload_bytes']
    return {
        'program': digest,
        'catalog': {'components_bytes': core, 'counted_subtotal_bytes': sum(core.values())},
        'optional_completion_plan': {'components_bytes': extra, 'counted_subtotal_bytes': sum(extra.values()),
            'scope': 'Explicit Plan::derive inventory; absent from executions that do not construct this optional plan.'},
        'table_representation_candidate': estimate,
        'limits': 'Selected retained structures only, not total runtime memory or RSS. Excludes allocator rounding, top-level headers, other catalog indexes, initial-state array, slot layouts, rule pure plans, merge metadata and serialized artifacts. State arrays and subset demand lists are counted once. No performance or new takeover claim.',
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('catalog', 'completion', 'program', 'output'):
        parser.add_argument('--'+key, type=Path, required=True)
    args = parser.parse_args()
    result = audit(load(args.catalog), load(args.completion), load(args.program))
    result['inputs_sha256'] = {k: sha(getattr(args, k)) for k in ('catalog', 'completion', 'program')}
    args.output.write_text(json.dumps(result, indent=2)+'\n')

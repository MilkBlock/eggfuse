"""Separate address-derived bindings from per-fact dynamic scalar payloads.

This is an offline census of stored values, not permission to remove lifecycle
state. Root equality never proves an immutable stored binding is address-derived.
"""
import collections
import json
import sys
from pathlib import Path


def census(storage, frames):
    metadata = {f['cell']: f for f in frames}
    counts = collections.Counter()
    visited = set()
    for component in storage['components']:
        shape = storage['shapes'][component['shape']]
        origins = {}
        for ordinal, ports in enumerate(shape['ports']):
            for local, symbol in enumerate(ports):
                origins.setdefault(symbol, (ordinal, local))
        for symbol, value in enumerate(component['signals']):
            counts['allocated_logical_signal_slots'] += 1
            if value is None:
                counts['unbound_slots'] += 1
                continue
            ordinal, local = origins[symbol]
            program = storage['programs'][shape['programs'][ordinal]]
            slots = [int(slot) for slot, port in program['native'].items() if port == local]
            # Only the unique first-origin slot is reconstructible here. A later
            # receiver's native slot would depend on activation order/aliasing.
            exact = len(slots) == 1 and value == ((component['frames'][ordinal] << 32) | (slots[0] + 1))
            counts['exact_origin_address_bindings' if exact else 'other_bindings'] += 1
        for ordinal, cell in enumerate(component['frames']):
            program = storage['programs'][shape['programs'][ordinal]]
            for fact in metadata.get(cell, {}).get('facts', []):
                if not fact['owned']:
                    continue
                identity = (cell, fact['op'])
                if identity in visited:
                    raise ValueError('owned fact has multiple component projections')
                visited.add(identity)
                fields = program['fields'][fact['op']]
                if not fields:
                    raise ValueError('owned fact lacks template field wiring')
                counts['owned_facts'] += 1
                scalars = sum(local is None for local in fields)
                counts['scalar_columns'] += scalars
                counts['facts_with_scalars' if scalars else 'facts_without_scalars'] += 1
                if not scalars:
                    counts['hidden_facts_without_scalars'] += bool(fact['hidden'])
                    # Binding availability is necessary, not sufficient for a
                    # fact to be visible or reusable after a stage transition.
                    for local in fields:
                        symbol = shape['ports'][ordinal][local]
                        if component['signals'][symbol] is None:
                            raise ValueError('live owned Eq field has no bound port')
    expected = {(f['cell'], s['op']) for f in frames for s in f['facts'] if s['owned']}
    if visited != expected:
        raise ValueError('owned fact lacks a component projection')
    return dict(counts)


def analyze(root):
    cases = []
    for name in ('fact', 'loopfact', 'sum-bits', 'dot-product'):
        data = json.loads((root/name/'candidate-static-types-heap.json').read_text())
        counts = census(data['ownership_storage'], data['source_storage']['fact_lifecycle']['frames'])
        assert counts['owned_facts'] == data['stable_fields']['live_stable_nodes']
        cases.append(dict(case=name, program=data['program_sha256'], counts=counts,
            graph_bytes=data['graph_owned_teardown_bytes'],
            stable_field_storage_bytes=dict(data['graph_fields'])['stable_ports'],
            # An optimistic ceiling excludes flags, exceptions and addressing.
            raw_origin_value_bytes=8*counts['exact_origin_address_bindings']))
    return dict(scope='saved standalone Cell runtime snapshots; no removed records or bytes claimed',
                obligations=['activation state', 'fact visibility and retirement', 'external Entry reads',
                             'worker snapshot isolation', 'bounded union fallback'], cases=cases)


if __name__ == '__main__':
    Path(sys.argv[2]).write_text(json.dumps(analyze(Path(sys.argv[1])), indent=2)+'\n')

"""Analyze existing Cell-to-Cell references without equating shape with identity.

Snapshot links are candidate wiring, not timeless congruence or removable indexes.
No instance/root ID is used as a portable template identity.
"""
import collections
import json
import sys
from pathlib import Path


def links(storage, lifecycle):
    components = {c['id']: c for c in storage['components']}
    positions = {cell: (c, ordinal) for c in components.values()
                 for ordinal, cell in enumerate(c['frames'])}
    if len(positions) != sum(len(c['frames']) for c in components.values()):
        raise ValueError('source instance belongs to multiple current components')
    facts = {(f['cell'], fact['op']): fact for f in lifecycle for fact in f['facts']}
    counts = collections.Counter()
    edges = []
    provider_cache = {}

    def providers(component, symbol):
        key = (component['id'], symbol)
        if key in provider_cache:
            return provider_cache[key]
        result = []
        shape = storage['shapes'][component['shape']]
        for ordinal, cell in enumerate(component['frames']):
            program = storage['programs'][shape['programs'][ordinal]]
            for operation, fields in enumerate(program['fields']):
                if not fields or fields[-1] is None or shape['ports'][ordinal][fields[-1]] != symbol:
                    continue
                fact = facts.get((cell, operation))
                if fact is not None and fact['owned'] and not fact['hidden']:
                    code = component['frame_codes'][ordinal]
                    result.append((ordinal, operation, storage['operators'][code][operation]))
        provider_cache[key] = result
        return result

    for consumer in components.values():
        for symbol, root in enumerate(consumer['roots']):
            if root is None:
                continue
            counts['bound_symbols'] += 1
            location = positions.get(root >> 32)
            if location is None:
                counts['no_native_frame'] += 1
                continue
            producer, ordinal = location
            shape = storage['shapes'][producer['shape']]
            program = storage['programs'][shape['programs'][ordinal]]
            local = program['native'].get(str((root & 0xffffffff)-1))
            if local is None:
                counts['no_native_slot'] += 1
                continue
            source_symbol = shape['ports'][ordinal][local]
            if producer['roots'][source_symbol] != root:
                counts['native_address_not_current_binding'] += 1
                continue
            if producer['id'] == consumer['id']:
                counts['native_symbol' if symbol == source_symbol else 'same_component_alias'] += 1
                continue
            counts['cross_component_symbols'] += 1
            sites = providers(producer, source_symbol)
            counts['cross_component_with_visible_provider'] += bool(sites)
            edges.append(dict(producer=producer['id'], producer_symbol=source_symbol,
                              consumer=consumer['id'], consumer_symbol=symbol,
                              visible_provider_sites=sites))
    return dict(counts), edges


def analyze(root):
    cases = []
    for name in ('fact', 'loopfact', 'sum-bits', 'dot-product'):
        data = json.loads((root/name/'candidate-residual-parent-heap.json').read_text())
        storage = data['ownership_storage']
        frames = data['source_storage']['fact_lifecycle']['frames']
        counts, edges = links(storage, frames)
        producers = collections.defaultdict(list)
        for edge in edges:
            producers[edge['producer']].append(edge)
        components = {c['id']: c for c in storage['components']}
        metadata = {f['cell']: f for f in frames}
        largest = []
        for producer, uses in sorted(producers.items(), key=lambda p: (-len(p[1]), p[0]))[:5]:
            component = components[producer]
            per_port = collections.Counter(e['producer_symbol'] for e in uses)
            largest.append(dict(component=producer, source_frames=component['frames'],
                source_templates=[metadata[f]['template'] for f in component['frames'] if f in metadata],
                live_facts=component['live_facts'], retained_symbols=len(component['signals']),
                cross_component_symbols=len(uses),
                consumer_components=len({e['consumer'] for e in uses}),
                referenced_output_ports=len(per_port), largest_port_fanouts=per_port.most_common(5),
                links_with_visible_provider=sum(bool(e['visible_provider_sites']) for e in uses)))
        pairs = {(e['producer'],e['consumer']) for e in edges}
        cases.append(dict(case=name, source_program=data['program_sha256'],
            components=len(components), counts=counts, directed_component_pairs=len(pairs),
            largest_producers=largest))
    return dict(scope='final snapshots of actual standalone Cell executions; candidate subcell links, not saved work',
        obligations=['actual rule-match/Entry evidence for joining children',
                     'typed operator identity and port projection',
                     'fact visibility and instance lifetime',
                     'original Run/effect order and uncovered boundary work'],
        limitations='Retained symbol links are not an exact count of live boundary-index records. A native binding without a visible provider does not prove a reusable live fact. Common inputs do not authorize merging whole components.',
        cases=cases)


if __name__ == '__main__':
    Path(sys.argv[2]).write_text(json.dumps(analyze(Path(sys.argv[1])), indent=2)+'\n')

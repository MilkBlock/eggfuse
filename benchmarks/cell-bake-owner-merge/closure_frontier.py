"""Audit cross-component native-address sharing in saved states, not Eq proofs."""
import collections
import hashlib
import json
from pathlib import Path
import sys


def port_incidence(snapshot, components, consumers):
    """Join exclusive port candidates to authoritative fact lifecycle records."""
    if 'source_storage' not in snapshot:
        return None
    storage = snapshot['ownership_storage']
    states = snapshot['source_storage']['fact_lifecycle']['frames']
    sources = {f['cell']: f for f in states}
    if len(sources) != len(states):
        raise ValueError('duplicate lifecycle source')
    facts = {}
    for source in states:
        for fact in source['facts']:
            identity = source['cell'], fact['op']
            if identity in facts or not fact['owned']:
                raise ValueError('invalid owned fact inventory')
            facts[identity] = fact
    counts = collections.Counter()
    touched = set()
    plans = collections.Counter()
    widths = collections.Counter()
    for (cid, symbol), receivers in consumers.items():
        if len(receivers) != 1:
            continue
        c = components[cid]
        shape = storage['shapes'][c['shape']]
        plans[c['shape'], symbol] += 1
        live = set()
        produced = set()
        input_uses = set()
        for step in shape['signals'][symbol]:
            ordinal, op = step['frame'], step['op']
            identity = c['frames'][ordinal], op
            program = storage['programs'][shape['programs'][ordinal]]
            fields = program['fields'][op]
            ports = shape['ports'][ordinal]
            if not any(local is not None and ports[local] == symbol for local in fields):
                raise ValueError('static incidence lacks claimed port')
            fact = facts.get(identity)
            if fact is None:
                counts['non_owned_static_sites'] += 1
                continue
            live.add(identity)
            touched.add(identity)
            if any(local is not None and ports[local] == symbol for local in fields[:-1]):
                input_uses.add(identity)
            if fields[-1] is not None and ports[fields[-1]] == symbol:
                produced.add(identity)
        counts['candidate_ports'] += 1
        counts['ports_without_owned_result_site'] += not produced
        counts['ports_with_multiple_owned_result_sites'] += len(produced) > 1
        counts['ports_with_local_input_uses'] += bool(input_uses)
        counts['ports_touching_hidden_facts'] += any(facts[f]['hidden'] for f in live)
        counts['ports_touching_retained_sources'] += any(sources[f[0]]['retainers'] for f in live)
        counts['ports_touching_lifecycle_exceptions'] += any(
            facts[f]['epoch'] != sources[f[0]]['started_epoch'] or
            facts[f]['born'] != sources[f[0]]['started_epoch'] for f in live)
        counts['live_site_visits'] += len(live)
        widths[len(live)] += 1
    counts['distinct_live_fact_sites'] = len(touched)
    counts['static_port_plans'] = len(plans)
    return dict(counts=dict(counts), live_sites_per_port=dict(sorted(widths.items())),
                scope='existing static incidences and current owned facts; no fact retirement or saturation proof')


def census(snapshot):
    storage = snapshot['ownership_storage']
    components = {c['id']: c for c in storage['components']}
    if len(components) != len(storage['components']):
        raise ValueError('duplicate component')
    origins = {}
    source_ids = set()
    for cid, c in components.items():
        shape = storage['shapes'][c['shape']]
        if (len(c['frames']) != len(shape['programs']) or
                len(c['signals']) != len(shape['signals']) or
                len(c['roots']) != len(c['signals'])):
            raise ValueError('incomplete component wiring')
        for ordinal, source in enumerate(c['frames']):
            if source in source_ids:
                raise ValueError('duplicate source identity')
            source_ids.add(source)
            program = storage['programs'][shape['programs'][ordinal]]
            for slot, local in program['native'].items():
                address = (source << 32) + int(slot) + 1
                symbol = shape['ports'][ordinal][local]
                if address in origins:
                    raise ValueError('duplicate native origin')
                origins[address] = (cid, symbol)
    counts = collections.Counter()
    consumers = collections.defaultdict(set)
    edge_widths = collections.Counter()
    port_consumers = collections.defaultdict(set)
    for cid, c in components.items():
        for symbol, (value, root) in enumerate(zip(c['signals'], c['roots'])):
            counts['signal_slots'] += 1
            if value is None:
                if root is not None:
                    raise ValueError('unbound signal has root')
                counts['unbound'] += 1
                continue
            if root is None:
                raise ValueError('bound signal lacks root')
            counts['root_changed'] += value != root
            origin = origins.get(value)
            if origin is None:
                counts['unknown_origin'] += 1
                continue
            producer, output = origin
            # An encoded address can name a result operation that returned a
            # foreign node. Require this origin to bind this exact raw value.
            if components[producer]['signals'][output] != value:
                counts['unconfirmed_origin'] += 1
                continue
            if producer == cid:
                counts['local_origin'] += 1
                continue
            counts['cross_component_slots'] += 1
            counts['cross_component_changed_roots'] += value != root
            consumers[producer].add(cid)
            port_consumers[producer, output].add(cid)
            edge_widths[producer, cid] += 1
    degree = collections.Counter(map(len, consumers.values()))
    port_degree = collections.Counter(map(len, port_consumers.values()))
    # A unique receiver is only a candidate for ownership; it does not prove
    # dead external FactRefs, source Run order or saturation. Reject cycles.
    successor = {p: next(iter(cs)) for p, cs in consumers.items() if len(cs) == 1}
    cyclic = set()
    finished = set()
    for start in successor:
        path, positions = [], {}
        node = start
        while node in successor and node not in finished and node not in positions:
            positions[node] = len(path)
            path.append(node)
            node = successor[node]
        if node in positions:
            cyclic.update(path[positions[node]:])
        finished.update(path)
    parent = {cid: cid for cid in components}

    def find(cid):
        while parent[cid] != cid:
            parent[cid] = parent[parent[cid]]
            cid = parent[cid]
        return cid

    for producer, consumer in successor.items():
        if producer not in cyclic:
            parent[find(producer)] = find(consumer)
    regions = collections.Counter(find(cid) for cid in components)
    counts.update(components=len(components), distinct_cross_edges=len(edge_widths),
                  referenced_producers=len(consumers), shared_producers=sum(d > 1 for d in map(len, consumers.values())),
                  referenced_native_ports=len(port_consumers),
                  exclusively_referenced_ports=sum(len(cs)==1 for cs in port_consumers.values()),
                  shared_native_ports=sum(len(cs)>1 for cs in port_consumers.values()),
                  exclusive_producers=len(successor), exclusive_cycle_nodes=len(cyclic),
                  candidate_regions=len(regions), largest_candidate_region=max(regions.values(), default=0))
    return dict(port_incidence=port_incidence(snapshot, components, port_consumers), counts=dict(counts), port_consumer_degree_histogram=dict(sorted(port_degree.items())), consumer_degree_histogram=dict(sorted(degree.items())),
                candidate_region_widths=dict(sorted(collections.Counter(regions.values()).items())),
                largest_shared_producers=[dict(component=p, consumers=len(cs),
                    source_frames=len(components[p]['frames']),
                    referenced_ports=sum(owner==p for owner, _ in port_consumers),
                    max_port_consumers=max(len(v) for (owner,_),v in port_consumers.items() if owner==p)) for p, cs in
                    sorted(consumers.items(), key=lambda item: (-len(item[1]), item[0]))[:12]])


def analyze(root):
    cases = []
    for case in ('fact', 'loopfact', 'sum-bits', 'dot-product'):
        data = (root / (case + '.json')).read_bytes()
        snapshot = json.loads(data)
        cases.append(dict(case=case, input_sha256=hashlib.sha256(data).hexdigest(),
                          program_sha256=snapshot['program_sha256'], **census(snapshot)))
    return dict(scope='offline native-address provenance in standalone Cell CPU final states',
                obligations=['Not an exhaustive use graph: unknown origins, scalars, external readers and facts remain live.',
                    'Current root equality is never treated as provenance or a saturation proof.',
                    'Unique-consumer regions are candidates only, not legal ownership transfers or memory savings.',
                    'Final-state topology cannot establish transient peak, source Run order or legal RHS skipping.'],
                cases=cases)


if __name__ == '__main__':
    Path(sys.argv[2]).write_text(json.dumps(analyze(Path(sys.argv[1])), indent=2)+'\n')

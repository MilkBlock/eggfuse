"""Offline dependency counterfactuals, never an ownership or reuse certificate."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from audit_history_dependencies import depths
from collect_observed_corpus import read_bytes
from historical_cell_sources import link_history


def observations(trace):
    """Keep every alternative from the first observing Run, not a unique owner."""
    first = {}; first_root = {}; replacements = {}; counts = Counter()
    for run in trace['runs']:
        current = defaultdict(list); current_root = defaultdict(list)
        for i, binding in enumerate(run['audit']['bindings']):
            rhs = binding['rhs']
            if not rhs['completed'] or any('unavailable' in s for s in rhs['slots']):
                continue
            slots = {s['slot']: s for s in rhs['slots']}
            for operation, effect in enumerate(trace['recipe']['rules'][binding['rule']]['effects']):
                if effect['kind'] != 'construct':
                    continue
                port = slots.get(effect['dst'], {}).get('eq_port')
                if port is None:
                    continue
                address = (run['ordinal'], i, operation)
                key = (port['sort'], port['identity'])
                root_key = (*key, port['after_run'])
                current[key].append(address); current_root[root_key].append(address)
                counts['constructor_observations'] += 1
                if key in first:
                    counts['reobserved_identity'] += 1
                if root_key in first_root:
                    counts['reobserved_identity_and_root'] += 1
        # Commit this Run as a group: do not privilege its first binding.
        for key, addresses in current.items():
            first.setdefault(key, addresses)
            for address in addresses:
                replacements.setdefault(address, {})['identity'] = first[key]
        for key, addresses in current_root.items():
            first_root.setdefault(key, addresses)
            for address in addresses:
                replacements[address]['identity_root'] = first_root[key]
    return replacements, dict(counts)


def analyze(trace):
    links = link_history(trace, fallback_only=True)
    replacements, counts = observations(trace)
    order = [(r['ordinal'], i) for r in trace['runs'] for i, _ in enumerate(r['audit']['bindings'])]
    edges = {mode: defaultdict(list) for mode in ('latest', 'identity', 'identity_root')}
    changed = {mode: Counter() for mode in ('identity', 'identity_root')}
    tables = {mode: Counter() for mode in changed}
    for window in links['windows']:
        for consumer in window['consumers']:
            dst = (window['consumer_run'], consumer['binding'])
            for port in consumer['ports']:
                if 'group' not in port:
                    continue
                historical = port.get('relation') == 'historical_observed_identity'
                port_sources = {mode: set() for mode in edges}
                for provider in window['groups'][port['group']]['providers']:
                    src = (provider.get('run', window['producer_run']), provider['binding'])
                    address = (*src, provider['operation'])
                    port_sources['latest'].add(address)
                    for mode in changed:
                        sources = replacements[address][mode] if historical else [address]
                        port_sources[mode].update(sources)
                        if historical and sources[0][0] != src[0]:
                            changed[mode]['historical_edges_redirected'] += 1
                            effect = trace['recipe']['rules'][provider['rule']]['effects'][provider['operation']]
                            tables[mode][effect.get('call', {}).get('table', 'unknown')] += 1
                # Multiple recent observers can point back to the same alternatives.
                # Count each source operation once per consumer port.
                for mode, sources in port_sources.items():
                    edges[mode][dst].extend(a[:2] for a in sorted(sources))
    baseline = depths(order, edges['latest'])
    results = {}
    for mode, graph in edges.items():
        depth = depths(order, graph)
        results[mode] = dict(layers=max(depth.values(), default=-1)+1,
                            edges=sum(map(len, graph.values())),
                            nodes_with_reduced_depth=sum(depth[a] < baseline[a] for a in order))
        if mode in changed:
            results[mode].update(changed[mode]); results[mode]['redirected_tables'] = dict(tables[mode])
    return dict(observation_counts=counts, counterfactuals=results,
                scope='Standalone CPU structural audit; no model inference or native runtime change',
                takeover_authorized=False, semantic_equivalence_proven=False,
                limitations=['Same identity and representative do not prove identical Cell context or liveness',
                             'Earliest observation is not necessarily the constructor owner',
                             'Adjacent routes are unchanged; historical alternatives from earliest Run are all retained',
                             'Depth is not GPU latency, accuracy, or a legal saturation schedule'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('trace', type=Path); parser.add_argument('output', type=Path)
    args = parser.parse_args(); raw = read_bytes(args.trace)
    data = json.loads(raw)
    if 'cases' in data:
        cases = []
        for case in data['cases']:
            if case['status'] != 'complete':
                continue
            source = read_bytes(Path(case['trace']))
            digest = hashlib.sha256(source).hexdigest()
            if digest != case['trace_sha256']:
                raise ValueError('trace fingerprint mismatch: '+case['case'])
            measured = analyze(json.loads(source))
            measured.update(case=case['case'], trace_sha256=digest)
            cases.append(measured)
        result = dict(cases=cases, manifest_sha256=hashlib.sha256(raw).hexdigest())
    else:
        result = analyze(data); result['trace_sha256'] = hashlib.sha256(raw).hexdigest()
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Count source-bound settled-state repetitions, not deletable runtime objects."""
import collections
import hashlib
import json
import sys
from pathlib import Path


def analyze(trace, catalog):
    h = trace['completed_history']
    if trace['all_saved_run_checks_equal'] is not True or h['dropped_events'] != 0:
        raise ValueError('complete audited history required')
    if h['program_sha256'] != catalog['program_sha256']:
        raise ValueError('program mismatch')
    units = {u['unit']: u for u in catalog['implementations']}
    original = {u['unit']: u for u in h['contracts']['implementations']}
    if len(units) != len(catalog['implementations']) or units.keys() != original.keys():
        raise ValueError('unit coverage mismatch')
    for uid, u in units.items():
        if u['source_path'] != original[uid]['source_path'] or u['ordered_class'] != original[uid]['class']:
            raise ValueError('source path mismatch')
    proofs = {r['unit']: r['after_source_runs'] for r in h['closure_transfers']['transfers']}
    events = h['events']
    if len(events) != len(h['event_units']):
        raise ValueError('event/unit mismatch')
    depths, reduced, rows = [], [], []
    counts = collections.Counter()
    for i, e in enumerate(events):
        parent = e['parent']
        if parent is not None and not 0 <= parent < i:
            raise ValueError('noncausal parent')
        depths.append(1 if parent is None else depths[parent] + 1)
        candidate = False
        if parent is not None:
            a, b = (units[h['event_units'][j]] for j in (parent, i))
            proof = proofs.get(b['unit'], {})
            if proof.get('kind') == 'saturated':
                counts['saturated_events'] += 1
                if proof['required_entry_facts'] or not proof['prefix_ports_injective'] or proof['strengthened_prefix_ports'] or proof['introduced_facts'] or proof['ordered_union_obligations']:
                    raise ValueError('inconsistent saturation certificate')
                cursor = i
                for _ in range(proof['prefix_stages']):
                    p = events[cursor]['parent']
                    if p is None or events[p]['run'] >= events[cursor]['run']:
                        raise ValueError('unsettled proof prefix')
                    cursor = p
                same = a['settled_class'] is not None and a['settled_class'] == b['settled_class']
                prefix = a['source_path'] == b['source_path'][:-1]
                candidate = same and prefix
                old_ports = a['ports'] or []
                new_ports = [port for port in (b['ports'] or []) if port[0] < len(a['source_path'])]
                stable_ports = old_ports == new_ports
                counts['same_ordered_class'] += a['ordered_class'] == b['ordered_class']
                counts['same_settled_class'] += same
                counts['same_state_exact_prefix'] += candidate
                counts['same_state_same_prefix_ports'] += candidate and stable_ports
                rows.append({'event': i, 'parent': parent, 'rule': e['entry'][0],
                    'source_rule': events[parent]['entry'][0], 'runs': [events[parent]['run'], e['run']],
                    'same_settled_class': same, 'exact_prefix': prefix, 'same_prefix_ports': stable_ports,
                    'ordered_normalizations': [a['ordered_normalization'], b['ordered_normalization']]})
        reduced.append((1 if parent is None else reduced[parent] + 1) - int(candidate))
    return {'scope': 'audited standalone Cell runtime history + compiler settled structures; not memory savings',
        'program_sha256': h['program_sha256'], 'events': len(events),
        'missing_parent_events': sum(e['truncated_parent'] for e in events),
        'counts': dict(counts),
        'depth_before': dict(sorted(collections.Counter(depths).items())),
        'depth_if_equal_settled_edges_folded': dict(sorted(collections.Counter(reduced).items())),
        'saturated_edges': rows,
        'remaining_obligations': ['Actual result identities and liveness are not represented by symbolic equality.',
            'Do not erase source Run publication, delta ownership or effect order.',
            'Keep the consumer continuation interface even when its settled state is shared.',
            'Potential depth folding is not an executable switch, instance retirement or heap measurement.']}


if __name__ == '__main__':
    source, catalog, output = map(Path, sys.argv[1:])
    result = analyze(json.loads(source.read_text()), json.loads(catalog.read_text()))
    result['trace_file_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    result['catalog_file_sha256'] = hashlib.sha256(catalog.read_bytes()).hexdigest()
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'saturated_edges'}, indent=2))

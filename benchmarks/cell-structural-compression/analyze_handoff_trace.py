#!/usr/bin/env python3
"""Recover observed cross-Run handoffs absent from single-cursor ancestry.

Join only exact input values against visible rows at the consumer Run boundary.
Never canonicalize with a later union state or treat missing bindings as equal.
"""
import collections
import hashlib
import json
import sys
from pathlib import Path


def key(values):
    return json.dumps(values, sort_keys=True, separators=(',', ':'))


def resolve(atom, values):
    result = []
    for arg in atom['args']:
        if 'slot' in arg:
            if str(arg['slot']) not in values:
                return None
            result.append(values[str(arg['slot'])])
        elif arg.get('sort', {}).get('kind') in ('i64', 'Unit'):
            result.append({'Int': arg['literal']})
        else:
            return None
    return key(result)


def analyze(program, trace):
    history = trace['completed_history']
    if (not trace['all_saved_run_checks_equal'] or history['program_sha256'] != program['sha256']
            or history['dropped_events']):
        raise ValueError('requires audited history without archive drops from the exact Program')
    table = trace['handoff']['table']
    producers = {}
    for i, event in enumerate(history['events']):
        if event.get('execution'):
            cell = event['execution']['cell']
            if cell in producers:
                raise ValueError('source execution identity reused')
            producers[cell] = (i, event)
    consumers = {}
    for rid, rule in enumerate(program['recipe']['rules']):
        atoms = [(i, a) for i, a in enumerate(rule['query']) if a['call'].get('table') == table]
        if atoms:
            consumers[rid] = atoms
    groups = collections.defaultdict(collections.Counter)
    gaps = collections.defaultdict(list)
    totals = collections.Counter()
    links = []
    missing_sources = []
    for window in trace['handoff']['windows']:
        before = collections.defaultdict(list)
        for row in window['before']:
            if not row['hidden']:
                before[key(row['values'])].append(row)
        for match in window['observation']['matches']:
            rid = match['rule']
            if rid not in consumers:
                continue
            totals['consumer_matches'] += 1
            totals['consumer_matches_without_query_continuation'] += match['continuation'] is None
            totals['consumer_matches_without_direct_token'] += not match['direct']
            for atom_id, atom in consumers[rid]:
                binding = resolve(atom, match['values'])
                if binding is None:
                    totals['missing_atom_inputs'] += 1
                    continue
                rows = before.get(binding, [])
                if len(rows) != 1:
                    totals['missing_or_ambiguous_boundary_row'] += 1
                    continue
                origin = rows[0]['origin']
                source = producers.get(origin['cell']) if origin else None
                if source is None:
                    totals['missing_producer_event'] += 1
                    missing_sources.append(dict(consumer_run=window['run'], consumer_rule=rid,
                                                origin=origin, witness=rows[0]['witness']))
                    continue
                event_id, event = source
                if event['run'] >= window['run']:
                    raise ValueError('boundary origin must precede consumer Run')
                producer = event['entry'][0]
                group = groups[(producer, rid)]
                group['matches'] += 1
                group['without_query_continuation'] += match['continuation'] is None
                group['without_direct_token'] += not match['direct']
                group['source_without_cursor_parent'] += event['parent'] is None
                gaps[(producer, rid)].append(window['run'] - event['run'])
                totals['exact_cross_run_links'] += 1
                links.append(dict(producer_event=event_id, producer_rule=producer,
                                  consumer_rule=rid, consumer_run=window['run'],
                                  consumer_ordinal=match['ordinal'], atom=atom_id))
    consumer_history = [e for e in history['events'] if e['entry'][0] in consumers]
    totals['consumer_history_events'] = len(consumer_history)
    totals['consumer_history_without_parent'] = sum(e['parent'] is None for e in consumer_history)
    writes = collections.Counter()
    attempts = collections.Counter()
    for window in trace['handoff']['windows']:
        for write in window['observation']['effective_writes']:
            writes[str(write['source'][1]) if write['source'] else 'repair'] += 1
        for match in window['observation']['matches']:
            rule = program['recipe']['rules'][match['rule']]
            attempts[str(match['rule'])] += sum(e['op'] == 'set' and e.get('call', {}).get('table') == table
                                             for e in rule['effects'])
    obligations = []
    for rid, atoms in consumers.items():
        covered = {i for i,_ in atoms}
        obligations.append(dict(rule=rid, residual_query=[a for i,a in
            enumerate(program['recipe']['rules'][rid]['query']) if i not in covered]))
    return dict(scope='observed exact boundary row provenance; not proven closure or saved work',
                program_sha256=program['sha256'], table=table, runs=trace['runs'],
                totals=dict(totals), residual_obligations=obligations,
                source_set_positions=dict(attempts), effective_writes=dict(writes),
                missing_producer_sources=missing_sources,
                groups=[dict(producer=p, consumer=c, **counts,
                             min_run_gap=min(gaps[p,c]), max_run_gap=max(gaps[p,c]))
                        for (p,c),counts in sorted(groups.items())], links=links)


if __name__ == '__main__':
    p, t, output = map(Path, sys.argv[1:])
    result = analyze(json.loads(p.read_text()), json.loads(t.read_text()))
    result['trace_file_sha256'] = hashlib.sha256(t.read_bytes()).hexdigest()
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('links','residual_obligations')}, indent=2))

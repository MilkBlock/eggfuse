#!/usr/bin/env python3
"""Relate observed RHS reuse to existing typed Entries without inventing ancestry."""
import collections
import json
import sys
from pathlib import Path
from analyze_rhs_before import analyze as validate


def analyze(program, audit):
    validate(audit)
    if program['sha256'] != audit['program_sha256']:
        raise ValueError('trace and typed program differ')
    trace = audit['rhs_projection_trace']['trace']
    completed = {e['cell']: e for e in trace['events']}
    if len(completed) != len(trace['events']):
        raise ValueError('ambiguous completed Cell identity')
    routes = collections.defaultdict(list)
    for route in program['multi_stage']['routes']:
        if 'residual' not in route:
            covered = {route['anchor'], *(step['atom'] for step in route['steps'])}
            width = len(program['recipe']['rules'][route['consumer']]['query'])
            route = dict(route, residual=sorted(set(range(width)) - covered))
        routes[(route['producer'], route['effect'], route['consumer'])].append(route)
    counts = collections.Counter()
    pairs = collections.defaultdict(collections.Counter)
    facts = collections.Counter()
    for b in trace['boundaries']:
        if b['prior_status'] != 'visible' or b['previous_run'] == b['run']:
            continue
        counts['cross_run_visible_boundaries'] += 1
        fact = (b['receipt'] or {}).get('Fact')
        if fact is None:
            counts['returned_fact_unavailable'] += 1
            continue
        facts[(fact['cell'], fact['op'])] += 1
        owner = completed.get(fact['cell'])
        if owner is None:
            counts['owner_not_in_completion_archive'] += 1
            continue
        if owner['run'] >= b['run']:
            counts['returned_owner_not_from_earlier_run'] += 1
            continue
        key = (owner['rule'], fact['op'], b['rule'])
        candidates = routes[key]
        for c in (counts, pairs[key]):
            c['earlier_returned_owner_observed'] += 1
            c['same_rule_owner'] += owner['rule'] == b['rule']
            c['exact_effect_entry_present'] += bool(candidates)
            c['exact_effect_entry_without_residual'] += any(not r['residual'] for r in candidates)
    return {
        'scope': 'offline analysis of actual standalone runtime and compiled Entries; not a takeover',
        'program_sha256': program['sha256'], 'counts': dict(counts),
        'unique_returned_facts': len(facts),
        'routes': [dict(producer=p, effect=op, consumer=c, **dict(n))
                   for (p, op, c), n in sorted(pairs.items(), key=lambda x: -x[1]['earlier_returned_owner_observed'])],
        'obligations': [
            'Returned receipt owner is not necessarily the last rule that reused it.',
            'These are post-operation returned receipts, not identities of the pre-operation checked donor.',
            'An Entry from another effect of the same rule does not establish reachability for this result.',
            'A route with residual query atoms is not a complete consumer match.',
            'Neither a route nor an equal key establishes actual cursor ancestry or scheduled availability.',
            'Trace scope omits non-pure and unrecorded owners; missing ownership is unknown, not impossible.',
            'Repeated requests returning an existing fact do not imply duplicate stored facts.',
            'Future takeover must use existing instance/component wiring, preserve residual enumeration and Run publication, and retire superseded state.'
        ]}


if __name__ == '__main__':
    result = analyze(json.loads(Path(sys.argv[1]).read_text()), json.loads(Path(sys.argv[2]).read_text()))
    Path(sys.argv[3]).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('counts', 'unique_returned_facts')}, indent=2))

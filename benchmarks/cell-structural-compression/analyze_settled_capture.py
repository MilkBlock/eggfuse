#!/usr/bin/env python3
"""Attribute actual capture work to equal settled transitions; don't double count plans."""
import collections
import hashlib
import json
import sys
from pathlib import Path
from analyze_settled_history import analyze


def summarize(trace, catalog, program):
    analysis = analyze(trace, catalog)
    if program['sha256'] != analysis['program_sha256']:
        raise ValueError('program mismatch')
    switch = program['iterative_bake']['rhs_handoffs']
    plans = {state['unit']: switch['completion_states'][i] for i, state in enumerate(switch['states'])}
    events = trace['completed_history']['events']
    groups = collections.defaultdict(collections.Counter)
    for row in analysis['saturated_edges']:
        if not row['same_settled_class'] or not row['exact_prefix']:
            continue
        event = events[row['event']]
        plan = plans.get(event['unit'])
        group = groups[(row['rule'], plan is not None)]
        group['events'] += 1
        work = event.get('capture')
        if work is None:
            group['missing_capture_observation'] += 1
            continue
        group['observed_captures'] += 1
        group['zero_allocation_captures'] += work['allocations'] == 0
        group['zero_slot_write_captures'] += work['slots'] == 0
        for key in ('allocations', 'slots', 'reads', 'inherited', 'shared_slots', 'empty_slots', 'heap_frames'):
            group[key] += work[key]
        execution = event.get('execution')
        if execution is not None:
            group['registered_source_frames'] += execution['registered']
            frame = execution['frame']
            group['observed_source_frames'] += frame is not None
            if frame is not None:
                group['source_logical_slots'] += frame['logical_slots']
                group['source_retained_facts'] += frame['retained_facts']
    all_rules = collections.defaultdict(collections.Counter)
    for event in events:
        work = event.get('capture')
        if work is None:
            continue
        row = all_rules[event['entry'][0]]
        row['events'] += 1
        for key in ('allocations', 'slots', 'reads', 'inherited', 'shared_slots'):
            row[key] += work[key]
    ranked = sorted(all_rules.items(), key=lambda item: (-item[1]['allocations'], item[0]))
    return {'scope': 'actual standalone Cell runtime capture work, not total heap or speed',
        'program_sha256': program['sha256'], 'runs': trace['runs'],
        'all_saved_run_checks_equal': True, 'events': len(events),
        'settled_state_counts': analysis['counts'],
        'capture_all_rules': [dict(rule=rule, **work) for rule, work in ranked if work['allocations'] or work['slots']],
        'groups': [dict(rule=rule, installed_direct_plan=plan, **work)
                   for (rule, plan), work in sorted(groups.items())],
        'limitations': ['Installed direct plan is not proof that runtime direct completion succeeded.',
            'Capture work excludes matching, publication, deferred root materialization and source frame allocation.',
            'Source frame sizes are per-event snapshots, not distinct live storage or committed mutations.',
            'Zero capture allocation can be existing sharing or an empty capture; it is not new savings.']}


if __name__ == '__main__':
    source, catalog, program, output = map(Path, sys.argv[1:])
    result = summarize(*(json.loads(p.read_text()) for p in (source, catalog, program)))
    result['trace_file_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))

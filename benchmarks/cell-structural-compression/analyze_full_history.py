#!/usr/bin/env python3
"""Classify actual completed ancestry; proof coverage is not saved execution."""
import collections
import hashlib
import json
import sys
from pathlib import Path

source, output = map(Path, sys.argv[1:])
raw = json.loads(source.read_text())
if raw.get('all_saved_run_checks_equal') is not True:
    raise SystemExit('missing Run-boundary acceptance')
h = raw['completed_history']
if h['dropped_events']:
    raise SystemExit('truncated archive; do not report complete-distribution counts')
events = h['events']
if len(events) != len(h['event_units']):
    raise SystemExit('event/unit mismatch')
proofs = {r['unit']: r['after_source_runs'] for r in h['closure_transfers']['transfers']}
paths = {r['unit']: r['source_path'] for r in h['contracts']['implementations']}
counts, depths, routes = collections.Counter(), collections.Counter(), collections.Counter()
uncompiled = 0
missing_parents = 0
root_counts = collections.Counter()
for i, (event, unit) in enumerate(zip(events, h['event_units'])):
    depth, cursor = 1, i
    while events[cursor]['parent'] is not None:
        parent = events[cursor]['parent']
        if not 0 <= parent < cursor:
            raise SystemExit('invalid ancestry')
        cursor, depth = parent, depth + 1
    depths[depth] += 1
    if event['truncated_parent']:
        missing_parents += 1
    uncompiled += event['unit'] is None
    if event['entry'][1] is None:
        root_counts[event['entry'][0]] += 1
    proof = proofs.get(unit)
    if proof is None:
        counts['no_transfer'] += 1
        continue
    cursor = i
    for _ in range(proof.get('prefix_stages', 0)):
        parent = events[cursor]['parent']
        if parent is None or events[parent]['run'] >= events[cursor]['run']:
            raise SystemExit('settled-source-Run obligation not established')
        cursor = parent
    kind = proof['kind']
    counts[kind] += 1
    routes[(kind, json.dumps(paths[unit], separators=(',', ':')))] += 1
result = {
    'scope': 'actual standalone Cell runtime completed ancestry; not all rule matches or saved operations',
    'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
    'program_sha256': h['program_sha256'],
    'runs': raw['runs'], 'all_saved_run_checks_equal': True,
    'event_limit': h['event_limit'], 'events': len(events), 'dropped_events': 0,
    'uncompiled_root_events': uncompiled, 'missing_parent_events': missing_parents,
    'recorded_ancestry_depth_distribution': dict(sorted(depths.items())),
    'closure_kinds': dict(sorted(counts.items())),
    'completed_producer_roots_by_rule': dict(sorted(root_counts.items())),
    'routes': [{'kind': kind, 'path': json.loads(path), 'events': n}
               for (kind, path), n in routes.most_common()],
    'limitation': 'Saturation is relative to the typed covered fragment. Coverage counts do not authorize omission of matches, visibility checks, or outstanding effects.',
}
output.write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k != 'routes'}, indent=2))

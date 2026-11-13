#!/usr/bin/env python3
"""Group typed closure proofs by actual completed lineage, without replay."""
import collections
import hashlib
import json
import sys
from pathlib import Path

source, destination = map(Path, sys.argv[1:])
raw = source.read_bytes()
trace = json.loads(raw)
if not trace['all_saved_run_checks_equal']:
    raise SystemExit('Run audit missing')
history = trace['completed_history']
proofs = {r['unit']: r for r in history['closure_transfers']['transfers']}
groups = collections.defaultdict(collections.Counter)
settled = collections.defaultdict(collections.Counter)
for row in proofs.values():
    groups[row['proof']['kind']]['compiled_paths'] += 1
if len(history['events']) != len(history['event_units']):
    raise SystemExit('event/lineage correspondence lost')
for index, (event, unit) in enumerate(zip(history['events'], history['event_units'])):
    proof = proofs.get(unit, {}).get('proof', {'kind': 'root'})
    group = groups[proof['kind']]
    group['completed_events'] += 1
    group['cross_run_events'] += event['parent'] is not None and event['producer_run'] != event['run']
    group['introduced_fact_opportunities'] += len(proof.get('introduced_facts', []))
    group['ordered_union_obligations'] += proof.get('ordered_union_obligations', 0)
    conditional = proofs.get(unit, {}).get('after_source_runs')
    if conditional:
        current = index
        eligible = True
        for _ in range(conditional['prefix_stages']):
            parent = history['events'][current]['parent']
            if parent is None or history['events'][parent]['run'] >= history['events'][current]['run']:
                eligible = False
                break
            current = parent
        kind = conditional['kind'] if eligible else 'source_run_boundary_unproved'
        settled[kind]['completed_events'] += 1
        if eligible:
            settled[kind]['introduced_fact_opportunities'] += len(conditional.get('introduced_facts', []))
            settled[kind]['ordered_union_obligations'] += conditional.get('ordered_union_obligations', 0)
for sample in history['sampled_applications']:
    proof = proofs[sample['to']]['proof']
    groups[proof['kind']]['overlapping_pair_support'] += sample['retained_support']
covered = [r['counts'] for r in trace['catalog_trace']['saturation']['rows']
           if r['outcome'] in ('rhs_covered', 'rhs_covered_by_inputs')]
result = {
    'scope': 'actual standalone runtime lineage with compile-only finite closure proofs',
    'runs': trace['runs'], 'all_saved_run_checks_equal': True,
    'events': len(history['events']), 'dropped_events': history['dropped_events'],
    'classifications': {k: dict(v) for k, v in sorted(groups.items())},
    'after_verified_source_run_boundaries': {k: dict(v) for k, v in sorted(settled.items())},
    'fully_covered_rhs_opportunities': {
        k: sum(row[k] for row in covered) for k in
        ('applications', 'covered_prefix_ops', 'prefix_copy_ops', 'prefix_static_alias_ops', 'prefix_remaining_effect_ops')
    },
    'limitation': 'No runtime skip or injection installed. Pair samples overlap event history; never add them. Remaining source effects may already be removed by dynamic completion and are not measured savings. Introduced facts are symbolic obligations, not committed mutations.',
    'input_sha256': hashlib.sha256(raw).hexdigest(),
}
destination.write_text(json.dumps(result, indent=2) + '\n')

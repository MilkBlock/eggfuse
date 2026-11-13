#!/usr/bin/env python3
"""Find witnessed cross-ruleset completion bundles; never infer absent matches."""
import collections
import hashlib
import json
import sys
from pathlib import Path

program_path, trace_path, output = map(Path, sys.argv[1:])
p, trace = (json.loads(path.read_text()) for path in (program_path, trace_path))
h = trace['completed_history']
if trace['all_saved_run_checks_equal'] is not True or h['program_sha256'] != p['sha256']:
    raise SystemExit('source-bound audited history required')
if h['dropped_events']:
    raise SystemExit('archive overflow must be accounted before ranking bundles')
es, units = h['events'], h['event_units']
proofs = {r['unit']: r['after_source_runs'] for r in h['closure_transfers']['transfers']}
rules = p['recipe']['rules']
kids = collections.defaultdict(list)
for i, e in enumerate(es):
    parent = e['parent']
    if parent is not None:
        if not 0 <= parent < i:
            raise SystemExit('noncausal event parent')
        kids[parent].append(i)

def proof(event, kind):
    result = proofs.get(units[event], {})
    if result.get('kind') != kind:
        return None
    cursor = event
    for _ in range(result['prefix_stages']):
        parent = es[cursor]['parent']
        if parent is None or es[parent]['run'] >= es[cursor]['run']:
            raise SystemExit('proof requires a missing or unfinished source Run')
        cursor = parent
    if result['required_entry_facts'] or not result['prefix_ports_injective'] or result['strengthened_prefix_ports']:
        raise SystemExit('internal transfer contains external assumptions')
    return result

bundles = collections.defaultdict(list)
for root, e in enumerate(es):
    if e['entry'][1] is not None:
        continue
    root_rule = e['entry'][0]
    for middle in kids[root]:
        if es[middle]['entry'][0] != 143 or not proof(middle, 'internal_completion'):
            continue
        for tail in kids[middle]:
            if es[tail]['entry'][0] != 137 or not proof(tail, 'saturated'):
                continue
            # A sibling is included only with the same actual producer and
            # published witness. Matching marginal rule frequencies is invalid.
            siblings = [x for x in kids[root] if es[x]['entry'][0] == 58
                        and es[x]['output'] == es[middle]['output']
                        and es[x]['witness'] == es[middle]['witness']
                        and proof(x, 'internal_completion')]
            if len(siblings) != 1:
                continue
            sibling = siblings[0]
            external = [x for x in kids[root] if x not in (middle, sibling)]
            external += [x for x in kids[middle] if x != tail]
            external += kids[sibling] + kids[tail]
            bundles[root_rule].append({'producer_event': root, 'rule58_event': sibling,
                'rule143_event': middle, 'rule137_event': tail,
                'runs': [es[x]['run'] for x in (root, sibling, middle, tail)],
                'boundary_events': sorted(set(external))})

switch = p['iterative_bake']['rhs_handoffs']
direct = {state['unit']: switch['completion_states'][i] is not None for i, state in enumerate(switch['states'])}
rows = []
for rid, members in sorted(bundles.items(), key=lambda pair: -len(pair[1])):
    event_ids = [x for row in members for k, x in row.items() if k.endswith('_event')]
    if len(event_ids) != len(set(event_ids)):
        raise SystemExit('overlapping bundle events require explicit ownership')
    boundaries = sorted({x for row in members for x in row['boundary_events']})
    roots = [i for i, e in enumerate(es) if e['entry'] == [rid, None]]
    lag = collections.Counter((row['runs'][2]-row['runs'][0], row['runs'][3]-row['runs'][2]) for row in members)
    rows.append({'producer_rule': rid, 'producer_ruleset': rules[rid]['metadata']['source_set'],
        'completion_ruleset': rules[143]['metadata']['source_set'],
        'cross_ruleset': rules[rid]['metadata']['source_set'] != rules[143]['metadata']['source_set'],
        'producer_events': len(roots), 'witnessed_bundles': len(members),
        'candidate_consumer_applications': 3*len(members),
        'local_saturated_tail_applications': len(members),
        'forks_in_same_source_run': sum(row['runs'][1] == row['runs'][2] for row in members),
        'existing_direct_plan_events': {key: sum(direct.get(es[row[key]]['unit'], False) for row in members)
            for key in ('rule58_event', 'rule143_event', 'rule137_event')},
        'source_run_gaps': [{'producer_to_143': a, '143_to_137': b, 'bundles': n} for (a,b),n in sorted(lag.items())],
        'external_consumers': dict(sorted(collections.Counter(es[x]['entry'][0] for x in boundaries).items())),
        'proofs': {str(es[x]['entry'][0]): proofs[units[x]] for x in
                   (members[0]['rule58_event'],members[0]['rule143_event'],members[0]['rule137_event'])},
        'instances': members})
result = {'scope': 'saved standalone Cell runtime ancestry + typed local closure proofs; no new execution or timing',
    'program_sha256': p['sha256'], 'trace_file_sha256': hashlib.sha256(trace_path.read_bytes()).hexdigest(),
    'events': len(es), 'missing_parent_events': sum(e['truncated_parent'] for e in es),
    'rule_sources': {str(r): rules[r]['metadata'] for r in sorted({58,61,137,143,145,317}|set(bundles))},
    'families': rows,
    'limitations': ['The selected rule region is locally closed only under the checked transfers, not all source rules.',
        'No observed child does not prove no future consumer; retain boundary exports and residual matching.',
        'Run ordinal gaps are observations, not executable scheduling constants.',
        'Candidate applications are logical executions; counts are not allocations, committed mutations or measured savings.',
        'Cross-stage liveness, delta ownership, competing derivations and publication ordering still require runtime lowering.']}
output.write_text(json.dumps(result, indent=2)+'\n')
for row in rows:
    print({k:v for k,v in row.items() if k not in ('instances','proofs')})

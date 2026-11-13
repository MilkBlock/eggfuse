#!/usr/bin/env python3
"""Audit offline admission against an already executed closure directory."""
import collections
import copy
import hashlib
import json
import sys
from pathlib import Path

paths = list(map(Path, sys.argv[1:]))
if len(paths) != 5:
    raise SystemExit('usage: analyze_closure_admission.py EFFECTIVE OLD_ADMITTED NEW_ADMITTED TRACE OUTPUT')
base, old, new, trace = [json.loads(p.read_text()) for p in paths[:4]]
def executable(raw):
    raw = copy.deepcopy(raw)
    raw.pop('sha256')
    raw['iterative_bake'].pop('closure_selection')
    # apply_plan revalidates this source checksum after provenance changes.
    raw['ownership_fragments'].pop('source')
    return raw
if executable(base) != executable(new):
    raise SystemExit('execution artifact changed beyond the three declared provenance fields')
if not trace['all_saved_run_checks_equal']:
    raise SystemExit('history lacks saved Run acceptance')
history = trace['completed_history']
proofs = {row['unit']: row['after_source_runs'] for row in history['closure_transfers']['transfers']}
groups = collections.Counter()
for index, (event, unit) in enumerate(zip(history['events'], history['event_units'])):
    proof = proofs.get(unit, {})
    if proof.get('kind') != 'internal_completion':
        continue
    cursor = index
    for _ in range(proof['prefix_stages']):
        parent = history['events'][cursor]['parent']
        if parent is None or history['events'][parent]['run'] >= history['events'][cursor]['run']:
            raise SystemExit('internal closure source boundary not established')
        cursor = parent
    if len(proof['introduced_facts']) != 1:
        raise SystemExit('expected single-fact cohort changed; inspect before summarizing')
    groups[event['entry'][0]] += 1
result = {
    'scope': 'offline compiler admission using saved actual lineage; no runtime speed measurement',
    'runtime_artifact_equal_to_effective_directory': True,
    'excluded_provenance_paths': ['/sha256', '/iterative_bake/closure_selection', '/ownership_fragments/source'],
    'internal_completion_events_by_consumer': dict(sorted(groups.items())),
    'internal_completion_events': sum(groups.values()),
    'old_added_units': old['iterative_bake']['closure_selection']['added_units'],
    'new_selection': new['iterative_bake']['closure_selection'],
    'direct_completion_states': [sum(x is not None for x in p['iterative_bake']['rhs_handoffs']['completion_states']) for p in (base, old, new)],
    'limits_total': [p['iterative_bake']['limits']['total'] for p in (base, old, new)],
    'limitations': 'Exact terminal-transfer admission is not whole-automaton equivalence or permanent domination. No existing state is removed. Introduced symbolic facts are obligations, not committed mutations. Runtime scope is unchanged.',
    'inputs_sha256': {p.as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths[:4]},
}
paths[4].write_text(json.dumps(result, indent=2) + '\n')

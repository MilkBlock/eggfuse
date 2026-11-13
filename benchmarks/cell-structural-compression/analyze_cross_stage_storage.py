#!/usr/bin/env python3
"""Attach physical completion snapshots to already witnessed closure bundles."""
import collections
import hashlib
import json
import sys
from pathlib import Path
trace_path, candidates_path, output = map(Path, sys.argv[1:])
t, candidates = (json.loads(p.read_text()) for p in (trace_path, candidates_path))
h=t['completed_history']; es=h['events']
if not t['all_saved_run_checks_equal'] or h['dropped_events']:
    raise SystemExit('complete audited archive required')
if candidates['trace_file_sha256'] != hashlib.sha256(trace_path.read_bytes()).hexdigest():
    raise SystemExit('candidate event ids belong to another trace')
if any(e.get('execution') is None for e in es):
    raise SystemExit('missing physical observations; unknown is not an empty frame')
roles=('producer_event','rule58_event','rule143_event','rule137_event')
rows=[]
for family in candidates['families']:
    summary={}
    for role in roles:
        observations=[es[b[role]]['execution'] for b in family['instances']]
        frames=[x['frame'] for x in observations if x['frame'] is not None]
        summary[role]={
            'events':len(observations), 'unique_execution_ids':len({x['cell'] for x in observations}),
            'frames_at_completion':len(frames),
            'registered_frames':sum(x['registered'] for x in observations),
            'transient_rhs_frames':sum(x['frame'] is not None and not x['registered'] for x in observations),
            'execution_ids_without_rhs_or_registered_frames':len(observations)-len(frames),
            'frames_with_facts':sum(f['retained_facts']>0 for f in frames),
            'logical_slot_observations':sum(f['logical_slots'] for f in frames),
            'retained_fact_observations':sum(f['retained_facts'] for f in frames),
            'non_hidden_fact_observations':sum(f['non_hidden_facts'] for f in frames),
            'parented_frames':sum(f['parent'] is not None for f in frames),
        }
    direct_anchors=0
    for b in family['instances']:
        witness=es[b['rule143_event']]['witness']
        if isinstance(witness,dict) and witness.get('Fact',{}).get('cell')==es[b['producer_event']]['execution']['cell']:
            direct_anchors+=1
    rows.append({'producer_rule':family['producer_rule'],'bundles':family['witnessed_bundles'],
        'anchor_owned_by_producer_execution':direct_anchors,'roles':summary})
result={'scope':'physical snapshots immediately after successful RHS, before source-Run repair; not peak storage or saved allocations',
    'program_sha256':h['program_sha256'],'runs':t['runs'],'events':len(es),
    'all_saved_run_checks_equal':True,'families':rows,
    'limitations':['Logical slots are not allocated bytes; inherited/shared storage can overlap.',
        'Facts observed at separate completion points are not a final or peak graph census.',
        'Existing facts may be owned by a different producer; execution id is not a universal result address.',
        'Absent rhs/registered frame does not exclude retained writer storage or prior execution cost; writer census remains separate.']}
output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(rows,indent=2))

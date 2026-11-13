#!/usr/bin/env python3
"""Compare audited closure work without treating coverage as saved operations."""
import hashlib
import json
import sys
from pathlib import Path

paths = list(map(Path, sys.argv[1:]))
if len(paths) != 4:
    raise SystemExit('usage: analyze_publication_forwarding.py BASELINE SHARED_SCAN DELIVERY OUTPUT')
lanes = [json.loads(p.read_text()) for p in paths[:3]]
for lane in lanes:
    if not lane['all_saved_run_checks_equal'] or lane['runs'] != 1428:
        raise SystemExit('missing complete Run acceptance')
    if lane['final_state'] != lanes[0]['final_state']:
        raise SystemExit('final states differ')
fields = ['ripsat_completed', 'ripsat_witness_fallbacks', 'history_allocations',
          'effect_frames', 'effect_slots_initialized', 'history_seal_reads',
          'history_seal_writes', 'history_publication_slot_probes',
          'history_publication_slot_writes', 'ripsat_witness_checks',
          'ripsat_projection_checks', 'ripsat_boundary_reads', 'ripsat_union_result_reads']
result = {
    'scope': 'actual standalone Cell runtime; work counts, no latency claim',
    'runs': 1428, 'all_saved_run_checks_equal': True, 'final_states_equal': True,
    'lanes': {name: {
        'stage': {k: lane['stage_work'][k] for k in fields if k in lane['stage_work']},
        'constructor_requests': lane['graph_work']['constructor_requests'],
        'union_requests': lane['graph_work']['union_requests'],
        'completion_frame_result_writes': lane['graph_work']['completion_frame_result_writes'],
        'key_lookup_calls': lane['key_lookup_calls'],
        'published_history_storage': lane['history_storage'],
    } for name, lane in zip(['baseline', 'rejected_shared_scan', 'delivery_forwarding'], lanes)},
    'decision': 'use existing output delivery to update shared result slots; do not add a shared-history sweep',
    'measured_work_after': lanes[2]['measured_work'],
    'limitations': 'The old lane lacks a full measured-work snapshot; no complete net work score is inferred. Added slot accesses/writes and changed boundary checks are charged. Matching is unchanged; 26 stale witnesses remain. Published-history storage is a partial census, not total egraph memory.',
    'inputs_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths[:3]},
}
paths[3].write_text(json.dumps(result, indent=2) + '\n')

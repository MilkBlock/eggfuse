#!/usr/bin/env python3
"""Validate saved audited trials and extract closure lifetime work, not timing."""
import hashlib
import json
import sys
from pathlib import Path

paths = list(map(Path, sys.argv[1:]))
if len(paths) != 4:
    raise SystemExit('usage: analyze_closure_lifetime.py DIAGNOSIS EAGER QUERY_REFRESH OUTPUT')
runs = [json.loads(p.read_text()) for p in paths[:3]]
for run in runs:
    if not run['all_saved_run_checks_equal'] or run['runs'] != 1428:
        raise SystemExit('missing full saved Run acceptance')
    if run['final_state'] != runs[0]['final_state']:
        raise SystemExit('final state differs')
fields = ['ripsat_completed', 'ripsat_witness_fallbacks', 'ripsat_witness_missing',
          'ripsat_witness_retired', 'ripsat_witness_wrong_table', 'ripsat_witness_hidden',
          'history_allocations', 'history_seal_reads', 'history_seal_writes',
          'history_seal_materialized_slots', 'history_seal_allocations',
          'ripsat_query_refreshes', 'ripsat_matched_result_reads']
result = {
    'scope': 'actual standalone Cell runtime; saved audited work, no latency claim',
    'runs': 1428, 'all_saved_run_checks_equal': True, 'final_states_equal': True,
    'lanes': {name: {
        'stage': {key: run['stage_work'][key] for key in fields if key in run['stage_work']},
        'constructor_requests': run['graph_work']['constructor_requests'],
        'key_lookup_calls': run['key_lookup_calls'],
    } for name, run in zip(['diagnosis', 'rejected_eager_sealing', 'rejected_query_refresh'], runs)},
    'decision': 'retain failure classification only; neither trial is enabled',
    'limitations': 'Eager sealing restores nine direct completions but scans and copies shared results; its seal_writes counts changed identities, not all materialized slots. Query refresh has no hits. These trials do not establish a speedup, rule-match elimination or memory compression.',
    'inputs_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths[:3]},
}
paths[3].write_text(json.dumps(result, indent=2) + '\n')

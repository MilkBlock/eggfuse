#!/usr/bin/env python3
"""Summarize actual-ancestry replay without promoting coverage to work credit."""
import collections
import json
import sys
from pathlib import Path
trace_path, replay_path, admitted_path, output = map(Path, sys.argv[1:])
h = json.loads(trace_path.read_text())['completed_history']
r = json.loads(replay_path.read_text())
a = json.loads(admitted_path.read_text())
if r['base_unit_mismatches'] or r['base_program'] != h['program_sha256']:
    raise SystemExit('replay does not reproduce recorded base dispatch')
counts = collections.Counter(tuple(row['entry']) for row in r['changes'])
result = {
    'scope': r['scope'],
    'base_program': r['base_program'], 'candidate_program': r['candidate_program'],
    'events': r['events'], 'base_unit_mismatches': 0,
    'direct_plan_opportunities': r['direct_plans'],
    'changed_transfer_events': len(r['changes']),
    'changed_by_entry': [{'entry': entry, 'events': n} for entry, n in sorted(counts.items())],
    'filtered_added_units': a['iterative_bake']['closure_selection']['added_units'],
    'actual_ancestry_rejections': [x for x in a['iterative_bake']['closure_selection']['redundant_terminal_transfers']
                                 if x['reason'] == 'actual-ancestry-already-has-same-terminal-transfer'],
    'limitation': 'Replay lacks runtime witness validity and cannot establish time or memory savings. Admission is profile guided, not permanent dominance.',
}
output.write_text(json.dumps(result, indent=2)+'\n')

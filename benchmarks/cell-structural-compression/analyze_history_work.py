#!/usr/bin/env python3
"""Account all existing work counters, including regressions and new costs."""
import json
import sys
from pathlib import Path
base_path, candidate_path, program_path, output = map(Path, sys.argv[1:])
base, candidate, program = [json.loads(p.read_text()) for p in (base_path, candidate_path, program_path)]
if not all(p['all_saved_run_checks_equal'] is True for p in (base, candidate)):
    raise SystemExit('both lanes require exact saved Run checks')
if base['runs'] != candidate['runs'] or candidate['program_sha256'] != program['sha256']:
    raise SystemExit('mismatched execution evidence')
a, b = base['measured_work'], candidate['measured_work']
if set(a) != set(b):
    raise SystemExit('counter schema differs; establish explicit correspondence')
deltas = {k: {'before': a[k], 'after': b[k], 'delta': b[k]-a[k]}
          for k in sorted(a) if a[k] != b[k]}
selection = program['iterative_bake']['closure_selection']
result = {
    'scope': 'actual standalone Cell runtime; work counts, not time or full egraph memory',
    'baseline_program': base['program_sha256'], 'candidate_program': candidate['program_sha256'],
    'runs': candidate['runs'], 'both_saved_run_checks_equal': True,
    'added_units': selection['added_units'],
    'new_paths': [r for r in selection['selected'] if r['added_roots'] or r['added_prefixes']],
    'counter_count': len(a), 'changed_counters': deltas,
    'direct_completions': [base['stage_work']['ripsat_completed'], candidate['stage_work']['ripsat_completed']],
    'history_storage_before': base['history_storage'],
    'history_storage_after': candidate['history_storage'],
    'limitation': 'Counters overlap; do not sum them into saved operations. Trace support is not an execution hit count. Retained history census is not peak or complete graph memory.',
}
output.write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(deltas, indent=2))

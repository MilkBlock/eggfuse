#!/usr/bin/env python3
"""Compare actual counters; keep existing-code activation and new routes apart."""
import hashlib
import json
import sys
from pathlib import Path

paths = list(map(Path, sys.argv[1:]))
baseline, existing, added = [json.loads(p.read_text()) for p in paths[:3]]
for run in (baseline, existing, added):
    if not run['all_saved_run_checks_equal'] or run['runs'] != baseline['runs']:
        raise SystemExit('Run acceptance missing')
    if run['final_state'] != baseline['final_state']:
        raise SystemExit('final states differ')

def changes(a, b, section):
    return {key: {'before': a[section].get(key), 'after': b[section].get(key)}
            for key in sorted(a[section].keys() | b[section].keys())
            if not key.endswith('_seconds') and a[section].get(key) != b[section].get(key)}

result = {
    'scope': 'actual standalone Cell runtime; work counts only, not timing',
    'runs': baseline['runs'], 'all_saved_run_checks_equal': True,
    'activation_changes': {s: changes(baseline, existing, s) for s in ('graph_work', 'stage_work', 'query_work')},
    'additional_route_changes': {s: changes(existing, added, s) for s in ('graph_work', 'stage_work', 'query_work')},
    'key_lookup_calls': [r['key_lookup_calls'] for r in (baseline, existing, added)],
    'published_history_storage': [r['history_storage'] for r in (baseline, existing, added)],
    'admission': 'existing-directory lowering has measured maintenance savings and nine extra constructor lookups; the additional route has no measured work benefit and is not the selected sum-bits configuration',
    'limitations': 'RHS direct completion still follows matching. No query-elimination, end-to-end speedup or complete memory result claimed. History storage is a partial census with shared layouts counted once; do not sum overlapping counters.',
    'inputs_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths[:3]},
}
paths[3].write_text(json.dumps(result, indent=2) + '\n')

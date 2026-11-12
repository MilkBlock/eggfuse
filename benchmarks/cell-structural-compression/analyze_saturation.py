#!/usr/bin/env python3
"""Summarize a passive audited trace; never infer saved work from observations."""
import collections
import hashlib
import json
import sys
from pathlib import Path

source, output = map(Path, sys.argv[1:])
raw = source.read_bytes()
trace = json.loads(raw)
if not trace['all_saved_run_checks_equal']:
    raise SystemExit('missing per-Run acceptance')
observation = trace['catalog_trace']['saturation']
groups = collections.defaultdict(collections.Counter)
for row in observation['rows']:
    group = groups[row['outcome']]
    group.update(row['counts'])
    group['cross_epoch_applications'] += row['counts']['applications'] if row['cross_epoch'] else 0
covered = {'rhs_covered', 'rhs_covered_by_inputs'}
result = {
    'scope': 'actual standalone Cell runtime, passive pre-execution RHS coverage; no rules skipped',
    'runs': trace['runs'], 'all_saved_run_checks_equal': True,
    'applications_observed': sum(g['applications'] for g in groups.values()),
    'fully_covered_rhs_candidates': sum(g['applications'] for k, g in groups.items() if k in covered),
    'outcomes': {k: dict(v) for k, v in sorted(groups.items())},
    'covered_rule_states': sorted((r for r in observation['rows'] if r['outcome'] in covered),
                                 key=lambda r: (-r['counts']['applications'], r['rule'])),
    'observer_component_checks': observation['component_checks'],
    'observer_fact_checks': observation['fact_checks'],
    'limitations': observation['limitations'],
    'input_sha256': hashlib.sha256(raw).hexdigest(),
}
output.write_text(json.dumps(result, indent=2) + '\n')

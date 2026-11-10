#!/usr/bin/env python3
"""Summarize saved complete checks and a bounded Raytrace prefix; never execute a workload."""
import argparse
import hashlib
import json
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('checks', type=Path)
p.add_argument('prefix_before', type=Path)
p.add_argument('prefix_after', type=Path)
p.add_argument('output', type=Path)
a = p.parse_args()
def read(path): return json.loads(path.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def extract(report):
    return {'query_workers': report.get('query_workers', {'enabled': False}),
            'key_lookup_calls': report['key_lookup_calls'],
            'stage_spine': {k:report['stage_spine']['stats'][k] for k in
                ['cell_query_entries','cell_query_steps','cell_query_result_writes',
                 'pre_resume_port_lookups','port_refreshes','resumed_steps']}}
checks = read(a.checks / 'checks.json')
semantic = read(a.checks / 'semantic-acceptance.json')
assert semantic['status'] == 'pass'
result = {'scope':checks['scope'], 'baseline_commit':checks['baseline_commit'],
          'binaries':checks['binaries'], 'semantic_acceptance':semantic,
          'cases':{}}
for case, evidence in checks['cases'].items():
    result['cases'][case] = {'program_sha256':evidence['program_sha256'], 'lanes':{}}
    for lane, data in evidence['lanes'].items():
        report = read(a.checks / f'{case}-{lane}' / 'report.json')
        result['cases'][case]['lanes'][lane] = dict(extract(report), hashes=data['hashes'], runs=data['runs'])
before, after = [read(root/'report.json') for root in [a.prefix_before, a.prefix_after]]
keys = ['ordinal','ruleset','path','iterations','epoch','logical_matches','executed_bindings','changed']
signature = lambda r: [[s[k] for k in keys] for s in r['steps']]
assert signature(before) == signature(after)
assert sha(a.prefix_before/'state.json') == sha(a.prefix_after/'state.json')
result['raytrace_prefix'] = {'scope':'first 128 source Runs only; exact prefix state and Run records; not full semantic acceptance or timing',
    'runs':len(after['steps']), 'before':extract(before), 'after':extract(after),
    'state_sha256':sha(a.prefix_after/'state.json'),
    'run_signature_sha256':hashlib.sha256(json.dumps(signature(after)).encode()).hexdigest()}
a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')

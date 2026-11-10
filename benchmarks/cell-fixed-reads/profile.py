#!/usr/bin/env python3
"""Collect the explicit all-rule serial query diagnostic; never time workloads."""
import hashlib
import json
from pathlib import Path
import sys


def read(p):
    return json.loads(p.read_text())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


FIELDS = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch', 'logical_matches', 'executed_bindings', 'changed')


def stamp(root):
    r = read(root / 'report.json')
    require(r['status'] == 'complete', 'incomplete diagnostic')
    schedule = [[s[k] for k in FIELDS] for s in r['steps']]
    return {'state_sha256': sha(root / 'state.json'),
        'schedule_sha256': hashlib.sha256(json.dumps(schedule, separators=(',', ':')).encode()).hexdigest()}


def collect(root, output):
    directory = root / 'ray-profile-all'
    r = read(directory / 'report.json')
    program = read(root / 'ray-program.json')
    require(not r['query_workers']['enabled'], 'serial attribution required')
    require(stamp(directory) == read(root / 'checkpoint/ray/samples.json')['semantic_reference'], 'Raytrace semantic diagnostic differs')
    require(stamp(root / 'sum-report-check') == stamp(root / 'sum-after4'), 'ordinary report changed sum execution')
    require(read(root / 'sum-report-check/report.json')['query_rule_profile'] is None, 'ordinary execution enabled profiling')
    rows = r['query_rule_profile']
    by_rule = {v['rule']: v for v in rows}
    require(len(by_rule) == len(rows), 'duplicate rule profiling')
    require(sum(v['bindings'] for v in rows) == r['stats']['bindings'], 'missing binding attribution')
    require(sum(v['residual_visits'] for v in rows) == r['stats']['residual_candidates'], 'missing residual attribution')
    for v in r['view_rule_profile']:
        require(all(by_rule[v['rule']][k] == value for k, value in v.items()), 'view projection differs')
    rules = program['recipe']['rules']
    family = {i for i, rule in enumerate(rules) if any(e['op'] == 'set' and e['call'].get('table') == 'Expr-size' for e in rule['effects'])}
    selected = [v for v in rows if v['rule'] in family]
    total = sum(v['search_s'] for v in rows)
    top = sorted(rows, key=lambda v: v['search_s'], reverse=True)[:15]
    output.write_text(json.dumps({
        'scope': 'explicit CELL_CPU_PROFILE=1; standalone serial Cell CPU; one instrumented diagnostic, not timing admission',
        'limits': 'Per-rule timers cover matches, not RHS/repair or Run preparation; worker completion is outside these timers. Profiling also visits normally skipped clean rules. Bindings are not committed mutations.',
        'behavior_commit': 'c00c8233', 'diagnostic': 'export existing per-rule aggregates for all rules, retaining the view-only projection',
        'runtime_sha256': sha(root / 'runtime-profile'), 'report_sha256': sha(directory / 'report.json'),
        'source_runtime_sha256': sha(Path('engine/cell-runtime/src/runtime.rs')),
        'program_file_sha256': sha(root / 'ray-program.json'), 'semantic_reference': stamp(directory),
        'rules_in_recipe': len(rules), 'profiled_rules': len(rows), 'old_view_rules': len(r['view_rule_profile']),
        'timed_query_seconds': total, 'search_phase_seconds': sum(s['phases']['search'] for s in r['steps']),
        'bindings': r['stats']['bindings'], 'residual_visits': r['stats']['residual_candidates'],
        'expr_size': {'rules': sorted(family), 'query_seconds': sum(v['search_s'] for v in selected),
            'query_fraction': sum(v['search_s'] for v in selected) / total,
            'bindings': sum(v['bindings'] for v in selected), 'residual_visits': sum(v['residual_visits'] for v in selected)},
        'top_rules': [dict(v, name=rules[v['rule']]['metadata']['name'], query=rules[v['rule']]['query'], effects=rules[v['rule']]['effects']) for v in top],
        'all_rules': rows,
    }, indent=2) + '\n')


if __name__ == '__main__':
    collect(Path(sys.argv[1]), Path(sys.argv[2]))

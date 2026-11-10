#!/usr/bin/env python3
"""Read saved executions to bound RHS opportunities; does not execute a workload."""
import argparse
import hashlib
import json
from pathlib import Path


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect(program, report):
    p, r = load(program), load(report)
    assert p['sha256'] == r['program_sha256']
    rules = p['recipe']['rules']
    constructors = {t['name'] for t in p['recipe']['tables'] if t['kind'] == 'constructor'}
    skipped = {(a['rule'], a['operation']) for a in p['known_results']['static_aliases']}
    counts = r['stage_spine']['stats']['bindings_by_rule']
    rows = []
    for rid, rule in enumerate(rules):
        visits = counts.get(str(rid), 0)
        if not visits:
            continue
        available = {i for i, s in enumerate(rule['slots']) if s['definition'] == 'query'}
        scalars = {i for i, s in enumerate(rule['slots']) if s['sort']['kind'] not in ['eq', 'container']}
        scalar, prefix = 0, 0
        before_effect = True
        constructor_prefix = 0
        before_other = True
        for op, e in enumerate(rule['effects']):
            if e['op'] == 'copy':
                arg = e['arg']
                if 'literal' in arg or arg.get('slot') in available:
                    available.add(e['dst'])
                continue
            call = e.get('call', {})
            if e['op'] == 'let' and 'primitive' in call and all(
                    'literal' in a or a.get('slot') in available & scalars for a in e.get('args', [])):
                scalar += 1
                prefix += int(before_effect)
                available.add(e['dst'])
            else:
                before_effect = False
            if (rid, op) in skipped:
                continue
            if before_other and e['op'] == 'let' and call.get('table') in constructors:
                constructor_prefix += 1
            else:
                before_other = False
        if scalar or constructor_prefix:
            rows.append({'rule': rid, 'observed_spine_bindings': visits,
                         'source_scalar_prefix_ops': prefix,
                         'input_only_scalar_ops': scalar,
                         'unaliased_constructor_prefix_ops': constructor_prefix})
    weighted = lambda field: sum(x['observed_spine_bindings'] * x[field] for x in rows)
    return {
        'program_sha256': p['sha256'], 'program_file_sha256': sha(program), 'report_file_sha256': sha(report),
        'runs': len(r['steps']),
        'observed': {k: r['stats'][k] for k in ['constructor_requests', 'constructor_reused', 'function_updates']},
        'weighted_opportunity': {k: weighted(k) for k in
            ['source_scalar_prefix_ops', 'input_only_scalar_ops', 'unaliased_constructor_prefix_ops']},
        'rules': rows,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['sum_program', 'sum_report', 'ray_program', 'ray_report', 'output']:
        p.add_argument(name, type=Path)
    a = p.parse_args()
    result = {
        'scope': 'Saved standalone Cell CPU executions; source-shape opportunity weighted by '
                 'observed Spine bindings, not worker coverage, committed mutations or measured speed.',
        'limits': 'Scalar expressions can fail. Constructor prefixes still need immutable input, '
                  'visibility, ownership and current equality proofs. Source order, winner selection '
                  'and actual result addresses remain authoritative. Current Run state and first misses '
                  'can reduce useful coverage; speculative duplicate work is not estimated here.',
        'sum': inspect(a.sum_program, a.sum_report),
        'ray': inspect(a.ray_program, a.ray_report),
    }
    a.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k]['weighted_opportunity'] for k in ['sum', 'ray']}, indent=2))


if __name__ == '__main__':
    main()

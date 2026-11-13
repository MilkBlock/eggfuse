"""Separate observed saturation opportunity from already eliminated RHS work.

No runtime IDs or old cross_epoch flags are used to pool rule definitions.
Counts are observations, not a proof that an application may be skipped.
"""
import collections
import hashlib
import json
import sys
from pathlib import Path
from pool import canonical


def covered_work(program, rows):
    aliases = {(x['rule'], x['operation']) for x in program['known_results']['static_aliases']}
    result = []
    for row in rows:
        if row['outcome'] not in ('rhs_covered', 'rhs_covered_by_inputs'):
            continue
        rule = program['recipe']['rules'][row['rule']]
        ops = rule['effects']
        counts = row['counts']
        n = counts['applications']
        kinds = collections.Counter()
        for index, op in enumerate(ops):
            if op['op'] == 'copy':
                kinds['copies'] += n
            elif (row['rule'], index) in aliases:
                kinds['static_aliases'] += n
            else:
                kinds['remaining_' + op.get('kind', op['op'])] += n
        assert counts['rhs_ops'] == n * len(ops), 'trace operation layout mismatch'
        assert kinds['copies'] == counts['prefix_copy_ops']
        assert kinds['static_aliases'] == counts['prefix_static_alias_ops']
        assert sum(v for k, v in kinds.items() if k.startswith('remaining_')) == counts['prefix_remaining_effect_ops']
        key = hashlib.sha256(canonical(rule).encode()).hexdigest()
        result.append(dict(rule_key=key, ruleset=rule['metadata']['source_set'],
                           local_rule=row['rule'], outcome=row['outcome'],
                           applications=n, work=dict(kinds)))
    return result


def analyze(root):
    cases, pooled = [], {}
    for name in ('fact', 'loopfact', 'sum-bits', 'dot-product'):
        directory = root / name
        program = json.loads((directory / 'candidate.json').read_text())
        observation = json.loads((directory / 'catalog-observation.json').read_text())
        heap = json.loads((directory / 'candidate-owned-fact-heap.json').read_text())
        assert program['sha256'] == observation['source_program'] == heap['program_sha256']
        assert observation['all_saved_run_checks_equal'] is True
        rows = observation['catalog_trace']['saturation']['rows']
        work = covered_work(program, rows)
        totals = collections.Counter()
        for row in work:
            totals.update(row['work'])
            key = row['rule_key']
            target = pooled.setdefault(key, dict(rule_key=key, ruleset=row['ruleset'], cases={}, work=collections.Counter()))
            target['cases'][name] = target['cases'].get(name, 0) + row['applications']
            target['work'].update(row['work'])
        states = collections.Counter()
        frames = heap['source_storage']['fact_lifecycle']['frames']
        component_of = {f:c['id'] for c in heap['ownership_storage']['components'] for f in c['frames']}
        for frame in frames:
            states['frames'] += 1
            states['facts'] += len(frame['facts'])
            if not frame['facts']:
                states['empty_frames'] += 1
                states['empty_retained_frames'] += bool(frame['retainers'])
            if frame['parent'] is not None:
                internal = frame['cell'] in component_of and component_of.get(frame['parent']['cell']) == component_of[frame['cell']]
                states['internal_parent_edges' if internal else 'boundary_parent_edges'] += 1
        cases.append(dict(case=name, source_program=program['sha256'],
                          applications=sum(r['counts']['applications'] for r in rows),
                          fully_covered_applications=sum(r['applications'] for r in work),
                          fully_covered_work=dict(totals), retained_state=dict(states)))
    ranked = sorted(pooled.values(), key=lambda x: (-sum(v for k,v in x['work'].items() if k.startswith('remaining_')), x['rule_key']))
    return dict(scope='saved actual standalone Cell executions; opportunity only, no saved mutations or speed claim',
                limitations='Older trace age flags are not reliable; age buckets are aggregated. Full RHS coverage does not prove all matches saturated, removable queries, delta ownership, or absence of future invalidation.',
                cases=cases, pooled_fully_covered_rules=ranked)


if __name__ == '__main__':
    Path(sys.argv[2]).write_text(json.dumps(analyze(Path(sys.argv[1])), indent=2)+'\n')

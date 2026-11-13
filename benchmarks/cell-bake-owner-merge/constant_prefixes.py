#!/usr/bin/env python3
"""Classify observed reuse against source Cell operations, without executing RHS."""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


def fixed_prefix(rule, tables):
    slots, result = {}, {}
    def arg(a):
        if 'literal' in a:
            return ('literal', json.dumps(a, sort_keys=True, separators=(',', ':')))
        return slots.get(a.get('slot'))
    for op, effect in enumerate(rule['effects']):
        if effect['op'] == 'copy':
            value = arg(effect['arg'])
            if value is None:
                break
            slots[effect['dst']] = value
            continue
        table = effect.get('call', {}).get('table')
        if effect['op'] != 'let' or tables.get(table, {}).get('kind') != 'constructor':
            break
        args = [arg(a) for a in effect['args']]
        if any(a is None for a in args):
            break
        value = ('constructor', table, tuple(args))
        slots[effect['dst']] = value
        result[op] = value
    return result


def classify(case, program):
    if case['program'] != program['sha256']:
        raise ValueError('transition/program mismatch')
    tables = program['source_core']['tables']
    by_name = {t['name']:t for t in tables}
    counts, groups = Counter(), {}
    for edge in case['template_transitions']['transitions']:
        if edge['stage'] != 'cross_run':
            continue
        uses = edge['uses']
        counts['observed_cross_run_uses'] += uses
        tid, op = edge['consumer_template'], edge['consumer_op']
        if tid >= len(program['templates']):
            counts['synthetic_or_unmapped_consumer'] += uses
            continue
        rid = program['templates'][tid]['rule']
        rule = program['recipe']['rules'][rid]
        effect = rule['effects'][op]
        table = tables[edge['table']]['name']
        if effect.get('call', {}).get('table') != table or effect['op'] != 'let':
            raise ValueError('observed operation differs from typed source')
        prefix = fixed_prefix(rule, by_name)
        if op not in prefix:
            counts['outside_proven_input_independent_prefix'] += uses
            continue
        counts['input_independent_prefix_uses'] += uses
        key = json.dumps(prefix[op], separators=(',', ':'))
        group = groups.setdefault(key, dict(expression=prefix[op], uses=0, sites={}))
        group['uses'] += uses
        site = group['sites'].setdefault((rid,op), dict(rule=rid,operation=op,uses=0,
            source_set=rule['metadata']['source_set'], next_effect=rule['effects'][max(prefix)+1:] ))
        site['uses'] += uses
        for remaining in site['next_effect']:
            if remaining['op'] == 'set':
                target = by_name[remaining['call']['table']]
                site['merge'] = target['merge_expr']
    result = []
    for group in groups.values():
        group['sites'] = list(group['sites'].values())
        result.append(group)
    return dict(case=case['case'], program=case['program'], counts=dict(counts),
                groups=sorted(result,key=lambda g:-g['uses']))


if __name__ == '__main__':
    transitions, root, output = map(Path,sys.argv[1:])
    raw = transitions.read_bytes()
    rows = []
    for case in json.loads(raw)['cases']:
        rows.append(classify(case,json.loads((root/case['case']/'candidate.json').read_text())))
    output.write_text(json.dumps(dict(scope='Offline typed-source classification of observed reuse; no runtime takeover or speed claim',
        input_sha256=hashlib.sha256(raw).hexdigest(),cases=rows),indent=2)+'\n')
    for row in rows:
        print(row['case'],row['counts'])

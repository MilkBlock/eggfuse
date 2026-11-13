"""Compile every recipe RHS into shared Cell token wiring.

Input/result references are exact structural ports, never float encodings of
eclass identifiers. A result port denotes the actual returned result, including
constructor reuse. This compiler does not execute queries or commit effects.
"""
import argparse
from collections import Counter
import json
from pathlib import Path


def compile_rule(rule):
    slots = rule['slots']
    sources = []
    env = {}
    operations = []
    scalar_ops = []
    marks = []
    copies_removed = 0

    def source(value):
        sources.append(value)
        return len(sources)-1

    for index, slot in enumerate(slots):
        if slot['definition'] == 'query':
            env[index] = source(dict(input_slot=index, sort=slot['sort']))

    def operand(arg):
        if 'slot' in arg:
            if arg['slot'] not in env:
                raise ValueError(f"read before definition: {arg['slot']}")
            return env[arg['slot']]
        if 'literal' in arg and 'sort' in arg:
            return source(dict(literal=arg['literal'], sort=arg['sort']))
        raise ValueError(f'unsupported operand: {arg}')

    for index, effect in enumerate(rule['effects']):
        kind = effect['kind']
        if kind == 'copy':
            env[effect['dst']] = operand(effect['arg'])
            copies_removed += 1
            continue
        args = [operand(a) for a in effect.get('args', [])]
        op = dict(operation=index, kind=kind, args=args)
        if 'call' in effect:
            op['call'] = effect['call']
        if kind == 'compute':
            # Its placement remains authoritative: a primitive failure aborts
            # subsequent original effects, not necessarily the whole binding.
            op['result'] = source(dict(scalar_operation=index, sort=effect['sort']))
            env[effect['dst']] = op['result']
            scalar_ops.append(index)
        elif kind == 'construct':
            op['result'] = source(dict(returned_port=index, sort=effect['sort']))
            env[effect['dst']] = op['result']
        elif kind == 'set':
            op['value'] = operand(effect['value'])
        elif kind == 'union':
            if len(args) != 2:
                raise ValueError('union arity')
        elif kind in ('subsume', 'delete', 'panic'):
            marks.append(dict(operation=index, reason='CPU ordered effect: '+kind))
        else:
            raise ValueError('unlowered RHS effect: '+kind)
        operations.append(op)

    return dict(sources=sources, operations=operations, scalar_operations=scalar_ops,
                boundary_marks=marks, copies_eliminated=copies_removed,
                input_slots=[i for i,s in enumerate(slots) if s['definition']=='query'])


def instantiate(plan, values):
    """Materialize reference evidence for audit, not a proposed runtime copy.

    Shared wiring can instead keep these references implicit in the template.
    No resolved constructor result is invented from a producer address.
    """
    inputs = {v['slot']:v['value'] for v in values}
    refs = []
    for node in plan['sources']:
        if 'input_slot' in node:
            value = inputs[node['input_slot']]
            if value['sort'] != node['sort']['name']:
                raise ValueError('input sort mismatch')
            refs.append(value)
        elif 'literal' in node:
            refs.append(dict(sort=node['sort']['name'], value=node['literal']))
        elif 'returned_port' in node:
            refs.append(dict(returned_port=node['returned_port'], sort=node['sort']['name']))
        else:
            refs.append(dict(scalar_operation=node['scalar_operation'], sort=node['sort']['name']))
    return refs


def main():
    p = argparse.ArgumentParser()
    p.add_argument('trace', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    trace = json.loads(args.trace.read_text())
    if not trace.get('all_slots'):
        raise ValueError('requires full typed input capture')
    plans = [compile_rule(r) for r in trace['recipe']['rules']]
    bindings = Counter()
    kinds = Counter()
    copies = 0
    for run in trace['runs']:
        for binding in run['audit']['bindings']:
            rid = binding['rule']
            plan = plans[rid]
            instantiate(plan, binding['values'])
            bindings[rid] += 1
            copies += plan['copies_eliminated']
            kinds.update(op['kind'] for op in plan['operations'])
    summary = dict(scope='Entire-recipe RHS token wiring and actual-binding instantiation audit; not GPU execution',
        program_sha256=trace['program_sha256'], compiled_rules=len(plans),
        instantiated_bindings=sum(bindings.values()),
        static_copies_eliminated=sum(p['copies_eliminated'] for p in plans),
        observed_copy_instructions_represented_as_aliases=copies,
        observed_ordered_operations=dict(kinds),
        rules_with_cpu_marks=sum(bool(p['boundary_marks']) for p in plans),
        gpu_completed_bindings=0, runtime_operations_removed=0,
        per_ruleset=[dict(ruleset=s['name'], rules=len(s['rule_ids']),
            instantiated_bindings=sum(bindings[r] for r in s['rule_ids']))
            for s in trace['recipe']['rulesets']])
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'rhs-plans.json').write_text(json.dumps(plans, indent=2)+'\n')
    (args.output/'rhs-summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='per_ruleset'}, indent=2))


if __name__ == '__main__':
    main()

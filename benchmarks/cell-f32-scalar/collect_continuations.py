"""Select witnessed next-Run scalar links from optional real_completion_dataset audits."""
import argparse
import hashlib
import json
from pathlib import Path
from compiler import I64_MIN, I64_MAX
from continuation import Continuation


def environment(rule, binding):
    env = {v['slot']: v['value'] for v in binding['values']}
    def read(arg):
        return env[arg['slot']] if 'slot' in arg else dict(sort=arg['sort']['name'], value=arg['literal'])
    for op in rule['effects']:
        if op.get('op') == 'copy':
            env[op['dst']] = read(op['arg'])
        elif op.get('kind') == 'compute':
            x, y = [read(a)['value'] for a in op['args']]
            name = op['call']['primitive']
            if name not in ('+', '-'):
                raise ValueError('unsupported evidence arithmetic')
            value = x+y if name == '+' else x-y
            assert I64_MIN <= value <= I64_MAX
            env[op['dst']] = dict(sort='i64', value=value)
    return env, read


def collect(runtime):
    records = []
    rules = None
    for case in runtime['cases']:
        assert case['fixed_point']['status'] == 'pass'
        all_rules = case['compiled_program']['recipe']['rules']
        p, c = all_rules[4], all_rules[2]
        assert p['metadata']['name'].startswith('(rewrite (Concat (SubTuple')
        assert c['metadata']['name'].startswith('(rewrite (SubTuple expr a b)')
        pair = [{k: r[k] for k in ('metadata', 'slots', 'query', 'effects')} for r in (p, c)]
        if rules is None:
            rules = pair
        assert pair == rules
        operation = next(i for i, op in enumerate(p['effects']) if op.get('call', {}).get('table') == 'SubTuple')
        table = next(t for t in case['compiled_program']['recipe']['tables'] if t['name'] == 'SubTuple')
        plan = Continuation(p, c, operation, 0, table)
        found = False
        for run, audit in enumerate(case['binding_audit'][:-1]):
            boundary = case['boundaries'][run]
            for binding in audit['bindings']:
                if binding['rule'] != 4:
                    continue
                env, read = environment(p, binding)
                op = p['effects'][operation]
                key = [read(a) for a in op['args']]
                visible = [r for r in boundary['graph']['rows'] if r['table'] == 'SubTuple'
                           and not r.get('subsumed', False) and r['values'][:-1] == key]
                for next_binding in case['binding_audit'][run+1]['bindings']:
                    if next_binding['rule'] != 2:
                        continue
                    cenv = {v['slot']: v['value'] for v in next_binding['values']}
                    actual = [cenv[a['slot']] for a in c['query'][0]['args']]
                    if not any(r['values'] == actual for r in visible):
                        continue
                    records.append(dict(id=case['id'], source=case['source'], source_sha256=case['source_sha256'],
                        program_sha256=case['program_sha256'], producer_run=boundary['ordinal'],
                        consumer_run=case['boundaries'][run+1]['ordinal'], producer=binding,
                        consumer=next_binding, visible_row=actual,
                        input_values=[env[s]['value'] for s in plan.plan.inputs]))
                    found = True
                    break
                if found:
                    break
            if found:
                break
        assert found, f"no witnessed next-Run link for {case['id']}"
    return dict(scope='Successful bindings linked through an actual visible next-Run row; not committed mutation counts',
                producer_rule=4, consumer_rule=2, operation=operation, atom=0, table=table, rules=rules, records=records)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--runtime', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = collect(json.loads(a.runtime.read_text()))
    result['runtime_sha256'] = hashlib.sha256(a.runtime.read_bytes()).hexdigest()
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2)+'\n')
    print(f"Selected {len(result['records'])} witnessed next-Run links")

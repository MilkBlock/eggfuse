"""Lower direct i64 projections from the Cell compiler recipe and audit both Runs."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


INPUT_ARITIES = {'A': 3, 'B': 3, 'Pair': 5, 'Request': 3, 'Result': 5}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def slot(operand):
    require(isinstance(operand, dict) and set(operand) == {'slot'}, 'expected a direct slot')
    number = operand['slot']
    require(type(number) is int and number >= 0, 'invalid slot number')
    return number


def lower_rule(rule, tables):
    rows = rule['interface']['rows']
    atoms = rule['query']
    require(len(atoms) == len(rows) == 2 and not rule['interface']['primitive_atoms'],
            'only two relation atoms supported')
    require(len(rule['effects']) == 1, 'requires a single constructor effect')
    effect, = rule['effects']
    require((effect['kind'], effect['op']) == ('construct', 'let'), 'expected relation construction')
    inputs = []
    locations = {}
    equalities = []
    for atom_index, (row, atom) in enumerate(zip(rows, atoms)):
        name = atom['call']['table']
        require(row['atom'] == atom_index and row['table'] == name and row['columns'] == atom['args'],
                'typed relation interface and query disagree')
        schema = tables[name]['schema']
        require(row['key_columns'] == list(range(len(schema)-1)) and len(atom['args']) == len(schema),
                'expected complete visible relation columns')
        inputs.append(name)
        for column, operand in enumerate(atom['args'][:-1]):
            number = slot(operand)
            require(rule['slots'][number]['sort'] == schema[column], 'query slot type mismatch')
            location = [atom_index, column]
            if number in locations:
                equalities.append([locations[number], location])
            else:
                locations[number] = location
        # Reading equality-sort constructor results would require e-class state.
        output_slot = rule['slots'][slot(atom['args'][-1])]
        require(output_slot['sort'] == schema[-1], 'unexpected constructor result type')
    hidden = [slot(atom['args'][-1]) for atom in atoms]
    require(len(set(hidden)) == len(hidden) and not set(hidden).intersection(locations),
            'shared constructor result introduces an unsupported equality')
    outputs = []
    for operand in effect['args']:
        number = slot(operand)
        require(number in locations, 'RHS is not a direct input column')
        outputs.append(locations[number])
    output_table = effect['call']['table']
    require(len(outputs) == len(tables[output_table]['schema'])-1, 'RHS arity mismatch')
    return dict(inputs=inputs, output_table=output_table, outputs=outputs, equalities=equalities)


def lower(recipe):
    tables = {table['name']: table for table in recipe['tables']}
    for table, arity in INPUT_ARITIES.items():
        schema = tables[table]['schema']
        require(tables[table]['kind'] == 'constructor' and len(schema) == arity+1
                and all(s['kind'] == 'i64' for s in schema[:-1]) and schema[-1]['kind'] == 'eq',
                f'unexpected table layout for {table}')
    rules = {}
    for rule in recipe['rules']:
        name = rule['metadata']['source_set']
        require(name not in rules, f'multiple rules in {name}')
        rules[name] = lower_rule(rule, tables)
    require(set(rules) == {'make', 'finish'}, 'expected both rulesets')
    require(set(rules['make']['inputs']) == {'A','B'} and rules['make']['output_table'] == 'Pair', 'invalid producer ABI')
    require(set(rules['finish']['inputs']) == {'Pair','Request'} and rules['finish']['output_table'] == 'Result', 'invalid consumer ABI')
    return rules


def visible(graph):
    result = {name: {} for name in INPUT_ARITIES}
    for row in graph['rows']:
        name = row['table']
        require(name in result and not row['subsumed'], 'unsupported graph row')
        values = row['values']
        require(len(values) == INPUT_ARITIES[name] + 1, f'unexpected row arity in {name}')
        args = tuple(v['value'] for v in values[:-1])
        require(args not in result[name], 'duplicate visible tuple')
        result[name][args] = values[-1]['eq']
    return result


def validate_case(case, rules):
    recipe = case['compiled_program']['recipe']
    before = visible(case['initial'])
    require(not before['Pair'] and not before['Result'], 'fixture must start before publication')
    a_rows, b_rows, requests = before['A'], before['B'], before['Request']
    pairs = {(i,j,k,x,y) for i,k,x in a_rows for j,l,y in b_rows if k == l}
    results = {(i,j,t,x,y) for i,j,k,x,y in pairs for a,b,t in requests if (a,b) == (i,j)}
    report = []
    for ordinal, name, expected in [(1,'make',pairs),(2,'finish',results)]:
        step = case['steps'][ordinal-1]
        boundary = case['boundaries'][ordinal-1]
        audit = case['binding_audit'][ordinal-1]
        require((step['ordinal'],boundary['ordinal'],step['ruleset'],audit['ruleset']) == (ordinal,ordinal,name,name),
                'unexpected Run schedule or audit')
        rule_id, rule = next((i,r) for i,r in enumerate(recipe['rules']) if r['metadata']['source_set'] == name)
        plan = rules[name]
        derived = []
        for bind in audit['bindings']:
            require(bind['rule'] == rule_id, 'wrong rule in binding trace')
            values = {entry['slot']: entry['value'] for entry in bind['values']}
            parents = []
            for atom in rule['query']:
                name_in = atom['call']['table']
                args = tuple(values[slot(op)]['value'] for op in atom['args'][:-1])
                parent_ref = values[slot(atom['args'][-1])]['eq']
                require(before[name_in].get(args) == parent_ref, 'binding references a missing source instance')
                parents.append(args)
            derived.append(tuple(parents[i][c] for i,c in plan['outputs']))
        require(Counter(derived) == Counter(expected), 'compiled projection disagrees with source join')
        after = visible(boundary['graph'])
        target = plan['output_table']
        require(set(after[target]) == expected, f'published {target} differs from source semantics')
        require(all(after[t] == before[t] for t in INPUT_ARITIES if t != target), 'unrelated table changed')
        require(len(derived) == step['logical_matches'], 'binding trace count mismatch')
        report.append(dict(run=ordinal, ruleset=name, logical_matches=step['logical_matches'],
                           published_count=len(after[target]), published_rows=sorted(after[target])))
        before = after
    require(len(case['steps']) == len(case['boundaries']) == len(case['binding_audit']) == 2,
            'unexpected extra Run')
    require(visible(case['final']) == before, 'final graph differs from final Run')
    require(case['source_sha256'] == digest(case['source'].encode()), 'source hash mismatch')
    return dict(id=case['id'], source_sha256=case['source_sha256'], program_sha256=case['program_sha256'],
                recipe_sha256=recipe['sha256'], runs=report)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('compiled_dataset', type=Path)
    parser.add_argument('plan', type=Path)
    parser.add_argument('audit', type=Path)
    args = parser.parse_args()
    cases = json.loads(args.compiled_dataset.read_text())['cases']
    require(bool(cases), 'empty compiler dataset')
    first = lower(cases[0]['compiled_program']['recipe'])
    reports = []
    for case in cases:
        rules = lower(case['compiled_program']['recipe'])
        require(rules == first, 'fixtures have different rule projections')
        reports.append(validate_case(case, rules))
    projection = {'schema':'eggfuse.crossrun.direct-input-projection/v1', 'rules':first}
    for path, data in [(args.plan, projection),(args.audit, {'schema':'eggfuse.crossrun.cpu-audit/v1', 'cases': reports})]:
        path.write_text(json.dumps(data,indent=2,sort_keys=True) + '\n')


if __name__ == '__main__':
    main()

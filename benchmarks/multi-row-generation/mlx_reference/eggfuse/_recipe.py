"""Read direct input-column projections from the typed Rust compiler recipe."""
INPUT_ARITIES = {'A': 3, 'B': 3, 'Pair': 5, 'Request': 3, 'Result': 5}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def slot(operand):
    require(isinstance(operand, dict) and set(operand) == {'slot'}, 'expected a direct slot')
    number = operand['slot']
    require(type(number) is int and number >= 0, 'invalid slot number')
    return number


def lower_rule(rule, tables):
    rows = rule['interface']['rows']
    atoms = rule['query']
    require(len(atoms) == len(rows) == 2 and (not rule['interface']['primitive_atoms']), 'only two relation atoms supported')
    require(len(rule['effects']) == 1, 'requires a single constructor effect')
    effect, = rule['effects']
    require((effect['kind'], effect['op']) == ('construct', 'let'), 'expected relation construction')
    inputs = []
    locations = {}
    equalities = []
    for atom_index, (row, atom) in enumerate(zip(rows, atoms)):
        name = atom['call']['table']
        require(row['atom'] == atom_index and row['table'] == name and (row['columns'] == atom['args']), 'typed relation interface and query disagree')
        schema = tables[name]['schema']
        require(row['key_columns'] == list(range(len(schema) - 1)) and len(atom['args']) == len(schema), 'expected complete visible relation columns')
        inputs.append(name)
        for column, operand in enumerate(atom['args'][:-1]):
            number = slot(operand)
            require(rule['slots'][number]['sort'] == schema[column], 'query slot type mismatch')
            location = [atom_index, column]
            if number in locations:
                equalities.append([locations[number], location])
            else:
                locations[number] = location
        output_slot = rule['slots'][slot(atom['args'][-1])]
        require(output_slot['sort'] == schema[-1], 'unexpected constructor result type')
    hidden = [slot(atom['args'][-1]) for atom in atoms]
    require(len(set(hidden)) == len(hidden) and (not set(hidden).intersection(locations)), 'shared constructor result introduces an unsupported equality')
    outputs = []
    for operand in effect['args']:
        number = slot(operand)
        require(number in locations, 'RHS is not a direct input column')
        outputs.append(locations[number])
    output_table = effect['call']['table']
    require(len(outputs) == len(tables[output_table]['schema']) - 1, 'RHS arity mismatch')
    return dict(inputs=inputs, output_table=output_table, outputs=outputs, equalities=equalities)


def lower(recipe):
    tables = {table['name']: table for table in recipe['tables']}
    for table, arity in INPUT_ARITIES.items():
        schema = tables[table]['schema']
        require(tables[table]['kind'] == 'constructor' and len(schema) == arity + 1 and all((s['kind'] == 'i64' for s in schema[:-1])) and (schema[-1]['kind'] == 'eq'), f'unexpected table layout for {table}')
    rules = {}
    for rule in recipe['rules']:
        name = rule['metadata']['source_set']
        require(name not in rules, f'multiple rules in {name}')
        rules[name] = lower_rule(rule, tables)
    require(set(rules) == {'make', 'finish'}, 'expected both rulesets')
    require(set(rules['make']['inputs']) == {'A', 'B'} and rules['make']['output_table'] == 'Pair', 'invalid producer ABI')
    require(set(rules['finish']['inputs']) == {'Pair', 'Request'} and rules['finish']['output_table'] == 'Result', 'invalid consumer ABI')
    return rules

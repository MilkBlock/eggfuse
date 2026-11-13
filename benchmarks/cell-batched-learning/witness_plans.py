"""Recheck observed witness positions against static Cell wiring.

This emits finite candidates, not runtime authorization. Exact symbol matches
prove Eq-key wiring under the original successful query. Scalars, literals and
unproved unions remain obligations; no trace value is used as a proof.
"""
import json
import sys
from pathlib import Path


def prove(program, storage, recipe):
    shape = storage['shapes'][recipe['shape']]
    rule = program['recipe']['rules'][recipe['rule']]
    tables = program['recipe']['tables']
    slots, obligations = {}, set()

    def fields(site, table):
        _, frame, operation = site
        code = recipe['frame_codes'][frame]
        actual = storage['operators'][code][operation]
        if actual >= len(tables) or tables[actual]['name'] != table:
            raise ValueError('witness operator differs from source operation')
        local = storage['programs'][shape['programs'][frame]]['fields'][operation]
        return [None if s is None else shape['ports'][frame][s] for s in local]

    for site in recipe['query_sites']:
        atom = rule['query'][site[0]]
        columns = fields(site, atom['call']['table'])
        if len(columns) != len(atom['args']):
            raise ValueError('query witness arity')
        for arg, symbol in zip(atom['args'], columns):
            if 'slot' not in arg or symbol is None:
                continue
            previous = slots.setdefault(arg['slot'], symbol)
            if previous != symbol:
                obligations.add('query_symbol_alias')

    def value(arg):
        return slots.get(arg.get('slot'))

    results = {site[0]: site for site in recipe['rhs_sites']}
    if len(results) != len(recipe['rhs_sites']):
        raise ValueError('duplicate RHS witness')
    used = set()
    for index, op in enumerate(rule['effects']):
        if op['op'] == 'copy':
            symbol = value(op['arg'])
            if symbol is not None:
                slots[op['dst']] = symbol
        elif op['op'] == 'let' and index in results:
            columns = fields(results[index], op['call']['table'])
            used.add(index)
            if len(columns) != len(op['args']) + 1:
                raise ValueError('RHS witness arity')
            for arg, symbol in zip(op['args'], columns):
                if symbol is None:
                    obligations.add('scalar_key_check')
                elif value(arg) is None:
                    obligations.add('external_eq_key_check')
                elif symbol != value(arg):
                    obligations.add('dynamic_key_equality')
            if columns[-1] is not None:
                slots[op['dst']] = columns[-1]
        elif op['op'] == 'union':
            a, b = map(value, op['args'])
            if a is None or b is None or a != b:
                obligations.add('dynamic_union_equality')
        else:
            obligations.add('unsupported_effect')
    if used != set(results):
        raise ValueError('unconsumed witness site')
    return sorted(obligations)


def analyze(root):
    reports = []
    for name in ('fact', 'loopfact', 'sum-bits', 'dot-product'):
        directory = root / name
        observation = json.loads((directory / 'witness-observation.json').read_text())
        program = json.loads((directory / 'candidate.json').read_text())
        assert observation['source_program'] == program['sha256']
        assert observation['all_saved_run_checks_equal'] and observation['terminal_check_equal']
        storage = observation['ownership_storage']
        plans = []
        for recipe in observation['catalog_trace']['saturation']['witness_recipes']:
            obligations = prove(program, storage, recipe)
            plans.append(dict(recipe, remaining_static_obligations=obligations))
        reports.append(dict(case=name, source_program=program['sha256'], runs=observation['runs'],
                            plans=plans, recipes=len(plans),
                            exact_wiring_recipes=sum(not p['remaining_static_obligations'] for p in plans),
                            exact_wiring_applications=sum(p['applications'] for p in plans if not p['remaining_static_obligations'])))
    return dict(scope='offline reproof of observed shape-relative witness wiring, not an executable takeover or memory saving',
                live_obligations=['original full query and delta ownership', 'fact liveness and visibility',
                                  'shape and frame generation', 'publication and Run ordering'], cases=reports)


if __name__ == '__main__':
    Path(sys.argv[2]).write_text(json.dumps(analyze(Path(sys.argv[1])), indent=2)+'\n')

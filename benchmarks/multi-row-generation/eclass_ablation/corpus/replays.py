"""Generate small Cell runtime replays from the actual typed Pass 3 rules and schemas."""
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
RULES = (23, 134, 135, 143, 145, 167, 168, 172, 173, 198, 199, 266, 267, 317, 572, 576, 580)


def resolve_slots(rule):
    sources = {}
    for idx, atom in enumerate(rule['query']):
        output = atom['args'][-1]
        if 'slot' in output:
            slot = output['slot']
            if slot not in sources:
                sources[slot] = ('query', idx, atom['call']['table'], atom['args'][:-1])
    for i, effect in enumerate(rule['effects']):
        if effect['kind'] == 'copy':
            sources[effect['dst']] = ('copy', effect['arg']['slot'])
        elif effect['kind'] == 'construct':
            sources[effect['dst']] = ('effect', i, effect['call']['table'], effect['args'])
    return sources


def minimal_case(program, rid, guard=True, committed=True):
    recipe = program['recipe']; rule = recipe['rules'][rid]; sources = resolve_slots(rule)
    all_tables = {t['name']:t for t in recipe['tables']}
    tables = {op['call']['table'] for op in rule['query']+rule['effects'] if 'call' in op}
    sorts = sorted({s['name'] for name in tables for s in all_tables[name]['schema'] if s['kind']=='eq'})
    prefix = [f'(sort {s})' for s in sorts]
    seedfn = {s:f'FixtureSeed{i}' for i,s in enumerate(sorts)}
    prefix.extend(f'(constructor {seedfn[s]} (i64) {s})' for s in sorts)
    # The tracked input type of this experiment has exactly one primitive function.
    for table in sorted(tables):
        spec = all_tables[table]; schema = [s['name'] for s in spec['schema']]
        args= ' '.join(schema[:-1]); out=schema[-1]
        if spec['kind']=='constructor': prefix.append(f'(constructor {table} ({args}) {out})')
        elif spec['kind']=='function' and out=='i64':prefix.append(f'(function {table} ({args}) {out} :merge (min old new))')
        else:raise ValueError(f'unsupported table {table}')
    unions=[(i,e) for i,e in enumerate(rule['effects']) if e['kind']=='union']
    if len(unions)!=1:raise ValueError('expected an explicit union')
    operation,union=unions[0]; left,right=[a['slot'] for a in union['args']]
    eq_sort=rule['slots'][left]['sort']; assert eq_sort==rule['slots'][right]['sort'] and eq_sort['kind']=='eq'
    prefix += [f"(relation Observe (i64 {eq_sort['name']}))", f"(relation Want (i64 {eq_sort['name']}))", '(relation Seen (i64 i64))',
               '(ruleset observe)', '(ruleset withheld)', f"(ruleset {rule['metadata']['source_set']})",rule['metadata']['name'],
               '(rule ((Observe i v) (Want j v)) ((Seen i j)) :ruleset observe)']
    instances=[]
    for inst in range(2):
        seed_offset=inst * 100
        def arg(x):
            if 'literal' in x:return str(x['literal']).lower()
            return term(x['slot'])
        def term(slot):
            ty=rule['slots'][slot]['sort']; spec=sources.get(slot)
            if spec is None:
                if ty['kind']=='eq':return f"({seedfn[ty['name']]} {seed_offset + slot + 1})"
                if ty['kind']=='i64':return str(seed_offset + slot+1)
                raise ValueError(ty)
            if spec[0]=='copy':return term(spec[1])
            if all_tables[spec[2]]['kind']=='function':return str(seed_offset + slot+1)
            return '('+' '.join([spec[2],*(arg(i) for i in spec[3])])+')'
        for atom in rule['query']:
            table=atom['call']['table']; args=atom['args']; expr='('+' '.join([table,*(arg(i) for i in args[:-1])])+')'
            if all_tables[table]['kind']=='function':
                value=int(arg(args[-1]))+int(not guard);prefix.append(f'(set {expr} {value})')
            else:prefix.append(expr)
        # Assign separate persistent scalar names to all distinct same-sort values.
        terms=[]; ports=[]; mapping={}
        for i,slot in enumerate(rule['slots']):
            if slot['sort']!=eq_sort:continue
            expr=term(i)
            if expr not in terms:
                terms.append(expr);ports.append({'slot':i,'sort':eq_sort['name'],'term':expr,'also_slots':[]})
            pos=terms.index(expr);mapping[i]=pos;ports[pos]['also_slots'].append(i)
        left_port,right_port=mapping[left],mapping[right];assert left_port!=right_port
        for i,expr in enumerate(terms):prefix.append(f'(Observe {inst * 16 + i} {expr})')
        prefix.append(f'(Want {inst} {terms[right_port]})')
        instances.append(ports)
    prefix.append(f"(run-schedule (seq (run observe) (run {rule['metadata']['source_set'] if committed else 'withheld'}) (run observe)))")
    source='\n'.join(prefix)+'\n'
    return dict(id=f'r{rid}-'+('withheld' if not committed else 'enabled' if guard else 'guard-false'),source=source,include_program=True,include_bindings=True,
                metadata=dict(rule=rid,operation=operation,ports=ports,union_slots=[left,right],pair=[left_port,right_port],guard=guard,committed=committed,instances=instances))


def cases(p):
    return [minimal_case(p,rid,committed=c) for rid in RULES for c in (True,False)]+[minimal_case(p,145,False)]


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('program',type=Path);parser.add_argument('output',type=Path);a=parser.parse_args()
    a.output.write_text(json.dumps({'cases':cases(json.loads(a.program.read_text()))},indent=2)+'\n')

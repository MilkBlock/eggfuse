"""Check a closed attribute-propagation saturation as one induction over the initialized input domain."""
from collections import defaultdict
from dataclasses import dataclass

import numpy as np


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def schedule_prefix(control):
    # Follow the first path in source order. An inner unary saturation guarantees
    # repeated scheduling of the second ruleset until it reports no change.
    found = []
    def visit(node, unary_saturation=False):
        if len(found) >= 2:
            return
        if 'run' in node:
            found.append((node['run'], unary_saturation))
        elif 'sequence' in node:
            children = node['sequence']
            for child in children:
                visit(child, unary_saturation and len(children) == 1)
        elif 'repeat' in node:
            require(node['repeat'] > 0, 'empty initial loop')
            visit(node['body'], False)
            require(len(found) >= 2 or node['repeat'] == 1, 'repeated setup')
        elif 'saturate' in node:
            visit(node['saturate'], True)
            require(len(found) >= 2, 'setup must run once')
        else:
            raise ValueError('unsupported source control')
    for node in control:
        visit(node)
    require(len(found) == 2 and not found[0][1] and found[1][1], 'unsupported saturation boundary')
    return found[0][0], found[1][0]


def initial_tables(packet):
    """Decode the same fact ids used by typed ingress without loading execution output."""
    symbols = packet['symbols']
    strings = sorted({v['value'] for v in symbols if v['sort'] == 'String'})
    values = []
    for v, rank in zip(symbols, packet['eq_order']):
        if 'eq' in v:
            values.append(rank)
        elif v['sort'] == 'String':
            values.append(strings.index(v['value']))
        else:
            require('value' in v and isinstance(v['value'], (bool, int)), 'unsupported ingress scalar')
            values.append(int(v['value']))
    rows = defaultdict(dict)
    count = 0
    for tid, params, hidden in packet['instances']:
        previous = []
        require(len(packet['templates'][tid])==len(hidden),'member visibility length')
        for (table, selectors), hidden_bit in zip(packet['templates'][tid], hidden):
            require(not hidden_bit, 'subsumed input')
            fields = tuple(previous[-field-1] if field < 0 else values[params[field]] for field in selectors)
            require(fields[:-1] not in rows[table], 'input key collision')
            rows[table][fields[:-1]] = fields[-1]
            previous.append(fields[-1])
            count += 1
    return rows, count, values


def initialize(rule, tables, rows, count, literals):
    require(not rule['q'] and rule['semi'] and not rule['inputs'], 'setup must be a one-shot empty LHS')
    env = {}
    writes = []
    for op, table, dest, args in rule['e']:
        bound = tuple(env[x] if x >= 0 else literals[-1-x] for x in args)
        if op == 'copy':
            env[dest], = bound
        elif op == 'construct':
            require(tables[table]['kind'] == 'constructor', 'unproved constructor')
            if bound not in rows[table]:
                rows[table][bound] = 1 + len(literals) + count
                count += 1
            env[dest] = rows[table][bound]
        elif op == 'set':
            require(tables[table]['kind'] != 'constructor', 'constructor set could union')
            key, value = bound[:-1], bound[-1]
            if key not in rows[table]:
                rows[table][key] = value
                writes.append((table,key,value))
                count += 1
            else:
                require(rows[table][key] == value or tables[table]['merge'] == 'old', 'unproved key repair')
        else:
            raise ValueError('setup with effects outside the admitted fragment')
    return count, writes


@dataclass
class Plan:
    initializer: int
    base_rule: int
    step_rule: int
    ruleset: str
    prior_class_slot: int
    result_slot: int
    value_slot: int
    constructor_slots: tuple
    inputs: tuple
    base_table: int
    attribute: int
    edges: int
    initial_value: int
    increment: int


def extract_plan(packet, helper, init_id, supported):
    rules, tables = packet['rules'], packet['tables']
    require(len(supported) == 2, 'saturation includes another active rule family')
    seeds = [rid for rid in supported if not rules[rid]['q']]
    require(len(seeds) == 1, 'ambiguous seed')
    seed, = seeds
    step, = supported - {seed}
    a, b = rules[seed], rules[step]
    require(a['semi'] and b['semi'] and not a['inputs'], 'one-shot seed and seminaive step required')
    require(len(a['e']) == 2 and len(b['q']) == 2, 'unexpected attribute shape')
    construct, write = a['e']
    base_table, key, attribute = construct[1], construct[2], write[1]
    require(construct[0] == 'construct' and tables[base_table]['kind']=='constructor' and not construct[3], 'base constructor')
    require(write[0]=='set' and len(write[3])==2 and write[3][0]==key and write[3][1]<0, 'base assignment')
    seed_literal = packet['symbols'][-write[3][1]-1]
    require(seed_literal['sort']=='i64','base integer')
    schema = tables[attribute]['schema']
    require(tables[attribute]['kind']=='function' and len(schema)==2 and schema[0]['kind']=='eq'
            and schema[1]['kind']=='i64','unary keyed attribute')
    (edges, columns), (prop, join) = b['q']
    require(isinstance(edges,int) and edges>=0 and tables[edges]['kind']=='constructor' and
            len(set(columns))==len(columns) and min(columns)>=0 and prop==attribute and
            len(join)==2 and join[0] in columns[:-1] and join[1]>=0 and join[1] not in columns,
            'require edge with child-key attribute read')
    result = columns[-1]
    require(tables[base_table]['schema'][-1]==schema[0] and tables[edges]['schema'][-1]==schema[0] and
            tables[edges]['schema'][columns.index(join[0])]==schema[0],'incompatible class sorts')
    # Symbolically reduce copies; only (+ parent_value constant) may reach the write.
    terms = {slot:('slot',slot) for slot in [*columns,join[1]]}
    def term(x):
        if x>=0:return terms[x]
        lit=packet['symbols'][-1-x]
        require(lit['sort']=='i64','noninteger offset')
        return ('literal',int(lit['value']))
    for op, call, dst, args in b['e'][:-1]:
        bound = [term(x) for x in args]
        if op == 'copy':terms[dst], = bound
        else:
            require(op=='compute' and call=='+' and len(bound)==2 and ('slot',join[1]) in bound,
                    'unsupported recursive scalar')
            offset, = [v for kind,v in bound if kind=='literal']
            terms[dst]=('plus',offset)
    op, table, _, args=b['e'][-1]
    require(op=='set' and table==attribute and len(args)==2 and term(args[0])==('slot',result) and
            term(args[1])[0]=='plus','recursive write')
    require(set(b['inputs'])==set(columns)|{join[1]},'binding projection loses edge identity')
    return Plan(init_id,seed,step,helper,join[0],result,join[1],tuple(columns),tuple(b['inputs']),
                base_table,attribute,edges,int(seed_literal['value']),term(args[1])[1])


def compile_domain(packet):
    init, helper=schedule_prefix(packet['control'])
    init_id, = packet['sets'][init]
    rows, count, literals=initial_tables(packet)
    initial_count=count
    count, writes=initialize(packet['rules'][init_id],packet['tables'],rows,count,literals)
    may_exist={table for table,relation in rows.items() if relation}
    # Monotone table-presence overapproximation. Disabled rules each need a
    # relation provably empty for the entire helper saturation, including writes.
    active=set()
    while True:
        old=len(active)
        for rid in packet['sets'][helper]:
            r=packet['rules'][rid]
            if all(not isinstance(t,int) or t in may_exist for t,_ in r['q']):
                active.add(rid)
                may_exist.update(t for op,t,_,_ in r['e'] if op in ('construct','set'))
        if len(active)==old:break
    plan=extract_plan(packet,helper,init_id,active)
    require(not rows[plan.attribute], 'external initial attribute writes')
    base=rows[plan.base_table].get((),None)
    require(base is not None, 'uninitialized base')
    edge_rows=sorted(((*key,res) for key,res in rows[plan.edges].items()),key=lambda row:row[-1])
    identities=[base,*[fields[-1] for fields in edge_rows]]
    require(len(set(identities))==len(identities),'merged constructors have alternative proofs')
    parent_pos=plan.constructor_slots.index(plan.prior_class_slot)
    parents=[-1,*[fields[parent_pos] for fields in edge_rows]]
    domain=np.array(list(zip(identities,parents)),dtype=np.int64)
    keys=set(identities)
    require(all(parent in keys for parent in parents[1:]),'open external parent')
    require(abs(plan.initial_value)+len(domain)*abs(plan.increment)<(1<<63),'overflow outside certificate domain')
    nullary_rules={i for i,r in enumerate(packet['rules']) if not r['q']}
    require(nullary_rules=={init_id,plan.base_rule},'not all empty-LHS rules are admitted')
    require(all(packet['rules'][rid]['semi'] for rid in nullary_rules),'empty-LHS rule may repeat')
    return plan,domain,edge_rows,writes,dict(initial_rows=initial_count,initialized_rows=count,
        initializer_effects=len(packet['rules'][init_id]['e']),helper_rules=len(packet['sets'][helper]),
        abstractly_enabled_rules=sorted(active))


def generate_reference_proposal(plan, domain):
    """Fixture generator, substitutable by any complete or incomplete neural proposal."""
    by_class={int(c):idx for idx,(c,_) in enumerate(domain)}
    claims=np.zeros((len(domain),5),dtype=np.int64)
    # Each token carries its identity, parent port, semantic wave and attribute.
    claims[0]=[1,domain[0,0],-1,0,plan.initial_value]
    for _ in range(len(domain)):
        for i,(ident,parent) in enumerate(domain[1:],1):
            prev=by_class[parent]
            if claims[prev,0] and not claims[i,0]:
                claims[i]=[1,ident,prev,claims[prev,3]+1,claims[prev,4]+plan.increment]
    require(bool(claims[:,0].all()),'domain not inductively reachable from base')
    return claims

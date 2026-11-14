"""Independent immutable constructor/union family oracle. No device plans or kernels.

All matches precede a Run's effects. Explicit union and full constructor
congruence change the fixed point even when no constructor is allocated.
"""
from device_snapshot_import import identity
from typed_literal import value as literal_value


class Reference:
    def __init__(self,recipe,rows,ids):
        import json
        self.recipe=recipe;self.parent=list(range(len(ids)));self.types=[None]*len(ids);self.scalar_values={};self.scalar_ids={}
        for value,i in ids.items():
            v=json.loads(value)
            if 'eq' in v:self.types[i]=v['sort']
            else:self.scalar_values[i]=v;self.scalar_ids[identity(v)]=i
        self.facts=[(r['table'],tuple(ids[identity(v)] for v in r['values'])) for r in rows]
        self.unions=0;self.constructions=0
        self.tables={t['name']:t for t in recipe.get('tables',[])}
        # An imported canonical constructor snapshot must already be closed.
        self.close()
        if self.unions:raise ValueError('noncanonical initial snapshot')

    def root(self,x):
        while self.parent[x]!=x:x=self.parent[x]
        return x

    def merge(self,a,b):
        if self.types[a] is None or self.types[a]!=self.types[b]:raise ValueError('ill-typed union')
        a,b=self.root(a),self.root(b)
        if a==b:return False
        self.parent[max(a,b)]=min(a,b);self.unions+=1;return True

    def close(self):
        while True:
            keys={};changed=False
            for table,values in self.facts:
                args=tuple(self.root(v) for v in values[:-1]);key=(table,args)
                if key in keys:changed=self.merge(keys[key],values[-1]) or changed
                else:keys[key]=values[-1]
            if not changed:return

    def matches(self,rule):
        bindings=[{}]
        for atom in rule['query']:
            following=[]
            if 'table' not in atom['call']:raise ValueError('unsupported oracle query')
            for a in atom['args']:
                if 'slot' not in a:literal_value(a)
            for binding in bindings:
                for table,values in self.facts:
                    if table!=atom['call']['table']:continue
                    if len(values)!=len(atom['args']):raise ValueError('oracle arity')
                    b=dict(binding)
                    for a,v in zip(atom['args'],values):
                        v=self.root(v)
                        if 'slot' not in a:
                            if self.scalar_values.get(v)!=literal_value(a):break
                            continue
                        slot=a['slot']
                        if slot in b and b[slot]!=v:break
                        b[slot]=v
                    else:following.append(b)
            bindings=list({tuple(sorted(b.items())):b for b in following}.values())
        return [b for b in bindings if all(identity(self.scalar_values.get(b.get(int(s))))==v for s,v in rule.get('query_literal_guards',{}).items())]

    def construct(self,table,args,value=None):
        schema=self.tables[table]['schema']
        if self.tables[table]['kind']!='constructor' or schema[-1]['kind']!='eq' or len(args)+1!=len(schema):raise ValueError('unsupported constructor')
        for t,values in self.facts:
            if t==table and tuple(self.root(v) for v in values[:-1])==tuple(self.root(v) for v in args):
                if value is not None:self.merge(values[-1],value)
                return values[-1]
        if value is None:
            value=len(self.parent);self.parent.append(value);self.types.append(schema[-1]['name'])
        self.facts.append((table,(*args,value)));self.constructions+=1
        return value

    def operand(self,arg,slots):
        if 'slot' in arg:return slots[arg['slot']]
        value=literal_value(arg);key=identity(value)
        if key not in self.scalar_ids:
            index=len(self.parent);self.parent.append(index);self.types.append(None)
            self.scalar_ids[key]=index;self.scalar_values[index]=value
        return self.scalar_ids[key]

    def apply(self,rules):
        matches=[self.matches(r) for r in rules];self.last_match_counts=list(map(len,matches));before=self.unions+self.constructions
        for rule,bindings in zip(rules,matches):
            for b in bindings:
                slots=dict(b)
                for op in rule['effects']:
                    if op['kind']=='copy':slots[op['dst']]=self.operand(op['arg'],slots)
                    elif op['kind']=='union':self.merge(*(self.operand(a,slots) for a in op['args']))
                    elif op['kind']=='construct':slots[op['dst']]=self.construct(op['call']['table'],[self.operand(a,slots) for a in op['args']])
                    elif op['kind']=='set':self.construct(op['call']['table'],[self.operand(a,slots) for a in op['args']],self.operand(op['value'],slots))
                    else:raise ValueError('unsupported reference effect')
        self.close()
        return self.unions+self.constructions-before,sum(map(len,matches))

    def saturate(self,rules,budget=64,observe=None):
        logs=[]
        for _ in range(budget):
            before=self.unions;ctors=self.constructions
            n,apps=self.apply(rules);record=dict(new_equivalences=self.unions-before,applications=apps,per_rule_applications=self.last_match_counts)
            if self.constructions!=ctors:record['new_constructors']=self.constructions-ctors
            logs.append(record)
            if observe is not None:observe(self,record)
            if not n:return logs
        raise ValueError('oracle saturation budget exhausted')

    def partition(self):return [self.root(i) for i in range(len(self.parent))]
    def normalized_facts(self):return {(t,tuple(self.root(v) for v in values)) for t,values in self.facts}


def compare_graph(reference,observed,roots,seed_count):
    """Anchor imported IDs, then map constructed results through complete facts.

    Independent of allocation order. Injectivity detects missing unions as well
    as surplus merges; all facts and allocated roots must be accounted for.
    """
    expected=reference.normalized_facts();bykey={(t,v[:-1]):v[-1] for t,v in expected}
    mapping={};errors=[]
    def bind(actual,wanted):
        if actual in mapping and mapping[actual]!=wanted:errors.append('inconsistent_result_class')
        else:mapping[actual]=wanted
    for i in range(seed_count):bind(int(roots[i]),reference.root(i))
    pending=list(set(observed))
    for _ in range(len(pending)+1):
        todo=[];progress=False
        for t,args,result in pending:
            args=tuple(int(roots[v]) for v in args);r=int(roots[result])
            if any(v not in mapping for v in args):todo.append((t,tuple(args),r));continue
            key=(t,tuple(mapping[v] for v in args))
            if key not in bykey:errors.append('unexpected_constructor');continue
            progress |= r not in mapping;bind(r,bykey[key])
        pending=todo
        if not pending or not progress:break
    if pending:errors.append('unresolved_constructor')
    if len(set(mapping.values()))!=len(mapping):errors.append('missing_union')
    if any(int(r) not in mapping for r in roots):errors.append('unexplained_allocation')
    actual={(t,tuple(mapping[int(roots[v])] for v in (*args,result))) for t,args,result in observed if all(int(roots[v]) in mapping for v in (*args,result))}
    if actual!=expected:errors.append('fact_set_difference')
    return dict(passed=not errors,errors=errors,actual_facts=len(actual),expected_facts=len(expected),mapped_classes=len(mapping))

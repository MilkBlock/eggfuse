"""Independent union-only immutable family oracle. No device plans or kernels.

All matches precede a Run's effects. Explicit union and full constructor
congruence change the fixed point even when no constructor is allocated.
"""
from device_snapshot_import import identity


class Reference:
    def __init__(self,recipe,rows,ids):
        import json
        self.recipe=recipe;self.parent=list(range(len(ids)));self.types=[None]*len(ids)
        for value,i in ids.items():
            v=json.loads(value)
            if 'eq' in v:self.types[i]=v['sort']
        self.facts=[(r['table'],tuple(ids[identity(v)] for v in r['values'])) for r in rows]
        self.unions=0
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
            if 'table' not in atom['call'] or any('slot' not in a for a in atom['args']):raise ValueError('unsupported oracle query')
            for binding in bindings:
                for table,values in self.facts:
                    if table!=atom['call']['table']:continue
                    if len(values)!=len(atom['args']):raise ValueError('oracle arity')
                    b=dict(binding)
                    for a,v in zip(atom['args'],values):
                        slot=a['slot'];v=self.root(v)
                        if slot in b and b[slot]!=v:break
                        b[slot]=v
                    else:following.append(b)
            bindings=list({tuple(sorted(b.items())):b for b in following}.values())
        return bindings

    def apply(self,rules):
        matches=[self.matches(r) for r in rules];before=self.unions
        for rule,bindings in zip(rules,matches):
            for b in bindings:
                slots=dict(b)
                for op in rule['effects']:
                    if op['kind']=='copy':slots[op['dst']]=slots[op['arg']['slot']]
                    elif op['kind']=='union':self.merge(*(slots[a['slot']] for a in op['args']))
                    else:raise ValueError('union oracle supports only copy/union effects')
        self.close()
        return self.unions-before,sum(map(len,matches))

    def saturate(self,rules,budget=64):
        logs=[]
        for _ in range(budget):
            n,apps=self.apply(rules);logs.append(dict(new_equivalences=n,applications=apps))
            if not n:return logs
        raise ValueError('oracle saturation budget exhausted')

    def partition(self):return [self.root(i) for i in range(len(self.parent))]
    def normalized_facts(self):return {(t,tuple(self.root(v) for v in values)) for t,values in self.facts}

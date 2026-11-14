"""Exhaustive bounded Eq interfaces, not arbitrary egraph contexts.

The boundary domain is a fixed completed source graph plus consumer query
facts, permitting aliases to all existing same-sort classes and fresh classes.
Contexts that would change a prior source root are outside this domain.
"""
from copy import deepcopy
from itertools import product,islice
from neural_typed_patterns import partitions


def input_cases(rule,limit=200000):
    groups={}
    for slot,desc in enumerate(rule['slots']):
        if desc['definition']!='query':continue
        sort=desc['sort']
        if sort['kind']!='eq':raise ValueError('finite Eq domain requires explicit scalar domains')
        groups.setdefault(sort['name'],[]).append(slot)
    options=[];count=1
    for slots in groups.values():
        choices=list(islice(partitions(len(slots)),limit+1));count*=len(choices)
        if count>limit:raise ValueError('finite input domain exceeds budget')
        options.append(choices)
    return [{slot:dict(sort=name,eq='class'+str(label))
             for (name,slots),labels in zip(groups.items(),selection) for slot,label in zip(slots,labels)}
            for selection in product(*options)]


def boundary_contexts(base,consumer,exports,limit=200000):
    inputs=[i for i,s in enumerate(consumer['slots']) if s['definition']=='query']
    if any(consumer['slots'][i]['sort']['kind']!='eq' for i in inputs):
        raise ValueError('finite boundary domain requires explicit scalar domains')
    seen=set();visited=0
    def assign(ref,bound,remaining):
        nonlocal visited
        if not remaining:
            visited+=1
            if visited>limit:raise ValueError('finite boundary domain exceeds budget')
            for query in consumer['query']:
                values=[bound[a['slot']] for a in query['args']]
                ref.construct(query['call']['table'],values[:-1],values[-1])
            ref.close()
            if any(ref.root(i)!=base.root(i) for i in range(len(base.parent))):return
            binding={s:ref.root(v) for s,v in bound.items()}
            signature=(tuple(sorted(binding.items())),tuple(sorted(ref.normalized_facts())))
            if signature not in seen:
                seen.add(signature);yield ref,binding
            return
        slot=remaining[0];sort=consumer['slots'][slot]['sort']['name']
        existing=sorted({ref.root(i) for i,t in enumerate(ref.types) if t==sort})
        for value in existing+[len(ref.parent)]:
            child=deepcopy(ref)
            if value==len(child.parent):child.parent.append(value);child.types.append(sort)
            yield from assign(child,{**bound,slot:value},remaining[1:])
    for table,values in exports:
        for atom in consumer['query']:
            if atom['call'].get('table')!=table or len(atom['args'])!=len(values):continue
            bound={};valid=True
            for arg,value in zip(atom['args'],values):
                slot=arg['slot'];value=base.root(value)
                if slot in bound and bound[slot]!=value:valid=False
                bound[slot]=value
            if valid:yield from assign(deepcopy(base),bound,[s for s in inputs if s not in bound])

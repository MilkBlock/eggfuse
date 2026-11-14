"""Independent immutable Cell-family reference, for post-execution CPU auditing."""
from device_snapshot_import import identity


def seeds(rows,ids):
    facts={}
    for row in rows:
        values=tuple(('seed',ids[identity(v)]) for v in row['values'])
        key=(row['table'],values[:-1])
        if key in facts and facts[key]!=values[-1]:raise ValueError('conflicting seed constructor')
        facts[key]=values[-1]
    return facts


def matches(rule,facts):
    bindings=[{}]
    for atom in rule['query']:
        if 'table' not in atom['call'] or any('slot' not in a for a in atom['args']):raise ValueError('unsupported reference query')
        following=[]
        for binding in bindings:
            for (table,args),result in facts.items():
                if table!=atom['call']['table']:continue
                values=(*args,result)
                if len(values)!=len(atom['args']):raise ValueError('constructor arity mismatch')
                b=dict(binding)
                for a,value in zip(atom['args'],values):
                    slot=a['slot']
                    if slot in b and b[slot]!=value:break
                    b[slot]=value
                else:following.append(b)
        bindings=list({tuple(sorted(b.items())):b for b in following}.values())
    return bindings


def apply_run(rules,facts):
    # All matching precedes every effect in the source Run.
    matched=[matches(rule,facts) for rule in rules];before=len(facts)
    for rule,bindings in zip(rules,matched):
        for binding in bindings:
            slots=dict(binding)
            for op in rule['effects']:
                if op['kind']=='copy' and 'slot' in op['arg']:slots[op['dst']]=slots[op['arg']['slot']]
                elif op['kind']=='construct' and all('slot' in a for a in op['args']):
                    key=(op['call']['table'],tuple(slots[a['slot']] for a in op['args']))
                    slots[op['dst']]=facts.setdefault(key,('construct',*key))
                else:raise ValueError('unsupported reference effect')
    return len(facts)-before,sum(map(len,matched))


def saturate(rules,rows,ids,max_runs=64):
    facts=seeds(rows,ids);changes=[];applications=[]
    for _ in range(max_runs):
        change,count=apply_run(rules,facts);changes.append(change);applications.append(count)
        if not change:return facts,changes,applications
    raise ValueError('reference saturation budget exhausted')


def scheduled(rules,rows,ids,control,max_runs=128):
    facts=seeds(rows,ids);logs=[]
    def visit(node):
        if isinstance(node,list):
            before=len(facts)
            for child in node:visit(child)
            return len(facts)>before
        if set(node)=={'sequence'}:return visit(node['sequence'])
        if set(node)=={'run'}:
            if len(logs)>=max_runs:raise ValueError('reference Run budget exhausted')
            selected=[r for r in rules if r['metadata']['source_set']==node['run']]
            if not selected:raise ValueError('uncovered reference stage')
            changed,apps=apply_run(selected,facts)
            logs.append(dict(stage=node['run'],new_facts=changed,applications=apps))
            return changed>0
        if set(node)=={'saturate'}:
            changed=False
            for _ in range(max_runs):
                more=visit(node['saturate']);changed |= more
                if not more:return changed
            raise ValueError('reference saturation budget exhausted')
        if set(node)=={'repeat','body'}:
            if type(node['repeat']) is not int or node['repeat']<0:raise ValueError('invalid repeat')
            changed=False
            for _ in range(node['repeat']):changed=visit(node['body']) or changed
            return changed
        raise ValueError('unsupported reference control')
    visit(control)
    return facts,logs


def facts_from_cells(recipe,state):
    """Decode ordinary operations directly, without the GPU view compiler."""
    import numpy as np
    from device_slot_owners import read
    result=[];complete=True
    for row in np.flatnonzero(state['present']&state['visible']):
        rid=int(state['keys'][row,0])
        if not 0<=rid<len(recipe['rules']):complete=False;continue
        rule=recipe['rules'][rid];pc=len(rule['effects']) if state['settled'][row] else int(state['effect_pc'][row])
        operations=[(-1,a['call']['table'],a['args']) for a in rule['query']]
        operations += [(i,o['call']['table'],[*o['args'],dict(slot=o['dst'])]) for i,o in enumerate(rule['effects']) if o['kind']=='construct']
        operations += [(i,o['call']['table'],[*o['args'],o['value']]) for i,o in enumerate(rule['effects']) if o['kind']=='set']
        for after,table,operands in operations:
            if pc<after+1:continue
            slots=np.array([a['slot'] for a in operands if 'slot' in a],np.int32)
            overwritten=any(op.get('dst') in slots for op in rule['effects'][after+1:pc])
            if overwritten or not read(state,'slot_valid',np.array(row),slots,np).all():complete=False;continue
            values=[];valid=True
            for arg in operands:
                if 'slot' in arg:values.append(int(read(state,'slots',np.array(row),np.array(arg['slot']),np)))
                else:
                    from typed_literal import value
                    try:key=identity(value(arg))
                    except ValueError:valid=False;break
                    if key not in recipe.get('literal_ids',{}):valid=False;break
                    values.append(recipe['literal_ids'][key])
            if not valid:complete=False;continue
            result.append((table,tuple(map(int,values[:-1])),int(values[-1])))
    return result,complete

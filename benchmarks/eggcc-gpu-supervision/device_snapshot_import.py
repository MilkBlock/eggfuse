"""Import an explicit visible constructor snapshot as seed Cell instances.

This is an initialization boundary, not reconstruction from future rule matches.
The local recipe keeps one original consumer and one seed template per input table.
"""
import copy,json
import numpy as np
from multi_entry_ridge import template,encode,scalar


def identity(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def prepare(recipe,snapshot,rid,spare,include_effects=False):
    return prepare_family(recipe,snapshot,[rid],spare,include_effects)


def prepare_family(recipe,snapshot,rules,spare,include_effects=True):
    from device_query_join import compile_query
    if not rules or len(set(rules))!=len(rules):raise ValueError('nonempty unique rule family required')
    originals=[recipe['rules'][rid] for rid in rules];tables={t['name']:t for t in recipe['tables']}
    required=sorted({a['call'].get('table') for original in originals for a in original['query'] if 'table' in a['call']})
    if include_effects:
        for op in (op for original in originals for op in original['effects']):
            if op['kind']=='copy' and 'slot' in op.get('arg',{}):continue
            if op['kind']=='union' and len(op['args'])==2 and all('slot' in a for a in op['args']):continue
            if op['kind']=='construct' and all('slot' in a for a in op['args']):
                required.append(op['call']['table']);continue
            raise ValueError('unsupported snapshot effect')
        required=sorted(set(required))
        if any(r['table'] in required and r.get('subsumed',False) for r in snapshot['rows']):
            raise ValueError('hidden constructor reuse requires separate coverage')
    if any(tables[t]['kind']!='constructor' for t in required):raise ValueError('constructor snapshot only')
    local=dict(tables=copy.deepcopy(recipe['tables']),rules=copy.deepcopy(originals))
    seed_rules={}
    for name in required:
        table=tables[name];seed_rules[name]=len(local['rules']);n=len(table['schema'])
        local['rules'].append(dict(metadata=dict(source_set='snapshot'),slots=[dict(sort=copy.deepcopy(s),definition='query') for s in table['schema']],
            query=[dict(call=dict(table=name),args=[dict(slot=i) for i in range(n)])],effects=[]))
    for rid in range(len(originals)):
        query=compile_query(local,rid)
        if not query['covered'] or not query['atoms']:raise ValueError('unsupported consumer query')
    rows=[];seen=set()
    for row in snapshot['rows']:
        if row['table'] not in seed_rules:continue
        if 'subsumed' not in row:raise ValueError('snapshot visibility missing')
        if row['subsumed']:continue
        schema=tables[row['table']]['schema']
        if len(row['values'])!=len(schema):raise ValueError('snapshot arity mismatch')
        for value,sort in zip(row['values'],schema):
            if value.get('sort')!=sort['name'] or ('eq' in value)!=(sort['kind']=='eq'):raise ValueError('snapshot sort mismatch')
        key=(row['table'],tuple(identity(v) for v in row['values']))
        if key not in seen:seen.add(key);rows.append(row)
    if not rows or spare<1:raise ValueError('nonempty snapshot and spare capacity required')
    width=max(len(r['slots']) for r in local['rules']);kw=1+max(sum(s['definition']=='query' for s in r['slots']) for r in local['rules'])
    n=len(rows)+spare
    state=dict(keys=np.full((n,kw),-1,np.int32),slots=np.full((n,width),-1,np.int32),slot_roots=np.full((n,width),-1,np.int32),slot_valid=np.zeros((n,width),bool),
        tokens=np.zeros((n,128),np.float32),generation=np.zeros(n,np.int32),effect_pc=np.zeros(n,np.int32),
        scalar_numbers=np.zeros((n,width),np.float32),scalar_numeric=np.zeros((n,width),bool),scalar_codes=np.zeros((n,width,64),np.float32),scalar_valid=np.zeros((n,width),bool))
    for name in ('present','visible','settled','active','readers','token_dirty'):state[name]=np.zeros(n,bool)
    ids={}
    for i,row in enumerate(rows):
        sr=seed_rules[row['table']];state['keys'][i,0]=sr;state['generation'][i]=1
        for name in ('present','visible','settled'):state[name][i]=True
        encoded=[]
        for j,value in enumerate(row['values']):
            key=identity(value);label=ids.setdefault(key,len(ids))
            state['slots'][i,j]=state['slot_roots'][i,j]=label;state['slot_valid'][i,j]=True;state['keys'][i,j+1]=label
            eq=(value['sort'],value['eq']) if 'eq' in value else None
            encoded.append((j,value,eq))
            if eq is None:
                v=value.get('value');numeric=isinstance(v,(int,float)) and not isinstance(v,bool) and np.isfinite(v) and abs(v)<=np.finfo(np.float32).max and float(np.float32(v))==v
                if numeric:state['scalar_numbers'][i,j]=v;state['scalar_numeric'][i,j]=True
                else:state['scalar_codes'][i,j]=scalar(value);state['scalar_valid'][i,j]=True
        roles,_=template(local['rules'][sr]);state['tokens'][i]=encode(encoded,roles,'class-balanced')
    return local,state,ids,rows


def reference_keys(rule,rows,ids,key_width,limit=100000):
    """Independent raw-value join, used only as CPU verification after inference."""
    bindings=[{}]
    for atom in rule['query']:
        following=[]
        for b in bindings:
            for row in rows:
                if row['table']!=atom['call']['table']:continue
                value=dict(b);ok=True
                for arg,field in zip(atom['args'],row['values']):
                    slot=arg['slot'];key=identity(field)
                    if slot in value and value[slot]!=key:ok=False;break
                    value[slot]=key
                if ok:following.append(value)
        bindings=list({tuple(sorted(b.items())):b for b in following}.values())
        if len(bindings)>limit:raise ValueError('CPU reference budget exceeded')
    inputs=[i for i,s in enumerate(rule['slots']) if s['definition']=='query']
    return {tuple([0]+[ids[b[i]] for i in inputs]+[-1]*(key_width-1-len(inputs))) for b in bindings}


def eq_registry(ids,sort_names,reserve=256):
    """Typed identity registry at an audited, already canonical seed boundary.

    Scalar IDs share the address namespace but can never authorize an Eq merge.
    Unallocated capacity is untyped until a constructor actually allocates it.
    """
    if reserve<0 or len(set(sort_names))!=len(sort_names):raise ValueError('invalid registry layout')
    if sorted(ids.values())!=list(range(len(ids))):raise ValueError('noncontiguous seed IDs')
    sorts=np.full(len(ids)+reserve,-1,np.int32)
    for value,index in ids.items():
        field=json.loads(value)
        if 'eq' in field:
            if field['sort'] not in sort_names:raise ValueError('uncovered seed Eq sort')
            sorts[index]=sort_names.index(field['sort'])
    return dict(roots=np.arange(len(sorts),dtype=np.int32),sorts=sorts)

"""Bounded exact multi-Cell constructor query matching from current slot views.

This fallback is dense candidate work, not a fast learned matching mechanism.
Overflow or incomplete views prohibit a complete-enumeration claim.
"""
from device_witness_views import compile_view,project
from device_slot_owners import shape as slot_shape, dtype as slot_dtype, read as read_slot, has as has_slot


def compile_query(recipe,rid,views=None):
    if views is None:views={}
    rule=recipe['rules'][rid];tables={t['name']:(i,t) for i,t in enumerate(recipe['tables'])}
    atoms=[];reasons=[];bound=set()
    for ordinal,atom in enumerate(rule['query']):
        table=tables.get(atom['call'].get('table'))
        if table is None or table[1]['kind']!='constructor':reasons.append('non_constructor_atom');continue
        if not atom['args'] or any('slot' not in a for a in atom['args']):reasons.append('literal_atom');continue
        slots=[a['slot'] for a in atom['args']]
        if any(not 0<=s<len(rule['slots']) for s in slots):raise ValueError('invalid query slot')
        key=(table[0],len(slots)-1)
        if key not in views:views[key]=compile_view(recipe,*key)
        guards={int(s):recipe.get('literal_ids',{}).get(v,-1) for s,v in rule.get('query_literal_guards',{}).items() if int(s) in slots}
        atoms.append(dict(slots=slots,literal_guards=guards,eq=[rule['slots'][s]['sort']['kind']=='eq' for s in slots],view=views[key]))
        bound.update(slots)
    required={i for i,s in enumerate(rule['slots']) if s['definition']=='query'}
    if not required<=bound:reasons.append('unbound_query_slots')
    return dict(rule=rid,width=len(rule['slots']),atoms=atoms,required=sorted(required),covered=not reasons,reasons=sorted(set(reasons)))


def order_query(plan,table_rows):
    """Bake one immutable query order from initialization cardinalities.

    Original atom ordinals and preferred witness origins remain authoritative.
    Estimates affect scheduling only, never completeness or equality proof.
    """
    if not plan['covered']:raise ValueError('cannot reorder unsupported query')
    counts=[table_rows[a['view']['table']] for a in plan['atoms']]
    if any(type(c) is not int or c<0 for c in counts):raise ValueError('invalid query estimate')
    return dict(plan,order=sorted(range(len(counts)),key=lambda i:(counts[i],i)))


def match(state,plan,capacity,external_complete,eq_settled,xp):
    if capacity<1:raise ValueError('positive binding capacity required')
    if not plan['covered']:raise ValueError('query contains unsupported atoms')
    width=plan['width'];values=xp.full((capacity,width),-1,slot_dtype(state));roots=xp.full_like(values,-1)
    source_rows=xp.full_like(values,-1);source_slots=xp.full_like(values,-1)
    live=xp.arange(capacity)==0;bound=set();eq_bound=set();overflow=xp.array(False)
    complete=xp.array(external_complete,dtype=xp.bool_)&xp.array(eq_settled,dtype=xp.bool_)
    witnesses=xp.full((capacity,len(plan['atoms'])),-1,xp.int32);records=xp.full_like(witnesses,-1)
    candidate_lanes=0;source_origin={}
    order=plan.get('order',list(range(len(plan['atoms']))))
    if sorted(order)!=list(range(len(plan['atoms']))):raise ValueError('invalid query order')
    for atom_index in order:
        atom=plan['atoms'][atom_index]
        view=project(state,atom['view'],external_complete,eq_settled,xp,include_fields=True)
        complete=complete&view['complete'];n=view['live'].shape[0];candidate_lanes+=capacity*n
        # Shared Cell views may expose the same logical fact repeatedly. Remove
        # those copies before bounded compaction, retaining the first witness.
        # Distinct result roots remain distinct, including unsettled collisions.
        fact_values=xp.where(xp.array(atom['eq'])[None,:],view['value_roots'],view['values'])
        same_fact=xp.all(fact_values[:,None,:]==fact_values[None,:,:],axis=2)
        earlier=xp.arange(n)[None,:]<xp.arange(n)[:,None]
        first_fact=view['live']&~xp.any(same_fact&earlier&view['live'][None,:],axis=1)
        keep=live[:,None]&first_fact[None,:];first={}
        for field,(slot,eq) in enumerate(zip(atom['slots'],atom['eq'])):
            current=view['value_roots'][:,field] if eq else view['values'][:,field]
            if slot in atom.get('literal_guards',{}):keep=keep&(current[None,:]==atom['literal_guards'][slot])
            if slot in bound:
                old=roots[:,slot] if eq else values[:,slot];keep=keep&(old[:,None]==current[None,:])
            if slot in first:
                other=view['value_roots'][:,first[slot]] if eq else view['values'][:,first[slot]]
                keep=keep&(current[None,:]==other[None,:])
            else:first[slot]=field
        flat=keep.reshape(-1);count=xp.sum(flat.astype(xp.int32));overflow=overflow|(count>capacity)
        # Deterministic compaction, retaining a visible overflow obligation.
        order=xp.sort(xp.where(flat,xp.arange(capacity*n),capacity*n))[:capacity]
        live=order<capacity*n;safe=xp.minimum(order,capacity*n-1);parent=safe//n;fact=safe%n
        values=values[parent];roots=roots[parent];source_rows=source_rows[parent];source_slots=source_slots[parent]
        atom_mask=xp.arange(len(plan['atoms']))[None,:]==atom_index
        witnesses=xp.where(atom_mask,view['source'][fact,None],witnesses[parent])
        records=xp.where(atom_mask,view['record'][fact,None],records[parent])
        for slot,field in first.items():
            if slot in source_origin and source_origin[slot]<atom_index:continue
            source_origin[slot]=atom_index
            mask=xp.arange(width)[None,:]==slot
            values=xp.where(mask,view['values'][fact,field,None],values)
            roots=xp.where(mask,view['value_roots'][fact,field,None],roots)
            source_rows=xp.where(mask,view['source'][fact,None],source_rows)
            source_slots=xp.where(mask,view['source_slots'][fact,field,None],source_slots)
        bound.update(first)
        eq_bound.update(slot for slot,eq in zip(atom['slots'],atom['eq']) if eq)
    # Repeated physical witnesses must not become repeated logical bindings.
    key=xp.where(xp.array([i in eq_bound for i in range(width)])[None,:],roots,values)
    same=xp.all(key[:,None,:]==key[None,:,:],axis=2)
    prior=xp.arange(capacity)[None,:]<xp.arange(capacity)[:,None]
    live=live&~xp.any(same&prior&live[None,:],axis=1)
    slot_valid=live[:,None]&xp.array([i in bound for i in range(width)])[None,:]
    generations=state['generation'][xp.clip(source_rows,0,slot_shape(state)[0]-1)]
    return dict(slots=values,slot_roots=roots,slot_valid=slot_valid,live=live,source_rows=source_rows,source_slots=source_slots,
                source_generations=generations,witness_rows=witnesses,witness_records=records,
                witness_generations=state['generation'][xp.clip(witnesses,0,slot_shape(state)[0]-1)],complete=complete&~overflow,overflow=overflow,missing_view=~complete,
                candidate_lanes=xp.array(candidate_lanes,dtype=xp.int32))


def match_inputs(state,plan,input_layout,capacity,external_complete,eq_settled,xp):
    from device_input_features import encode_inputs
    bindings=match(state,plan,capacity,external_complete,eq_settled,xp)
    rows=xp.clip(bindings['source_rows'],0,slot_shape(state)[0]-1)
    slots=xp.clip(bindings['source_slots'],0,slot_shape(state)[1]-1)
    shape=bindings['slots'].shape
    inputs=dict(roots=bindings['slot_roots'],valid=bindings['slot_valid'],numbers=xp.zeros(shape,xp.float32),
                numeric=xp.zeros(shape,xp.bool_),scalar_codes=xp.zeros(shape+(64,),xp.float32),scalar_valid=xp.zeros(shape,xp.bool_))
    for column,key in [('scalar_numbers','numbers'),('scalar_numeric','numeric'),('scalar_codes','scalar_codes'),('scalar_valid','scalar_valid')]:
        if has_slot(state,column):inputs[key]=read_slot(state,column,rows,slots,xp)
    features,marks=encode_inputs(inputs,input_layout,xp)
    features['input_ready']=features['input_ready']&bindings['live']
    return bindings,features,marks


def main():
    import argparse,json,hashlib
    from pathlib import Path
    from collections import Counter
    import numpy as np
    from collect_observed_corpus import read_bytes
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    raw=read_bytes(a.trace);recipe=json.loads(raw)['recipe'];views={}
    plans=[compile_query(recipe,i,views) for i in range(len(recipe['rules']))]
    supported=[p for p in plans if p['covered']]
    result=dict(scope='Static immutable-constructor query coverage; not runtime enumeration or full ruleset coverage',trace_sha256=hashlib.sha256(raw).hexdigest(),
        rules=len(plans),supported_rules=len(supported),supported_multi_atom_rules=sum(len(p['atoms'])>1 for p in supported),
        max_supported_atoms=max((len(p['atoms']) for p in supported),default=0),
        boundary_counts=dict(Counter(reason for p in plans for reason in p['reasons'])),
        shared_view_layouts=len(views),shared_static_view_bytes=sum(v.nbytes for view in views.values() for v in view.values() if isinstance(v,np.ndarray)),
        complete_ruleset_authorized=False,ownership_transfer_authorized=False)
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()

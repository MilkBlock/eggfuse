"""Effect-backed two-step Cell tuples, derived from synthetic rule executions.

The second input receives the whole producer token. Exact interfaces establish
connectivity; reference effects are labels only. Ownership plans are compiled
opportunities, not permission to reclaim a live runtime row.
"""
from copy import deepcopy
import numpy as np
from multi_entry_ridge import template,encode
from device_slot_owners import compile_transfer
from neural_cell_samples import apply_instance


def completed(rule,binding,ref):
    values={s:ref.root(v) for s,v in binding.items()}
    facts={(t,vs[:-1]):vs[-1] for t,vs in ref.normalized_facts()}
    for op in rule['effects']:
        if op['kind']=='copy':values[op['dst']]=values[op['arg']['slot']]
        elif op['kind']=='construct':values[op['dst']]=facts[(op['call']['table'],tuple(values[a['slot']] for a in op['args']))]
        elif op['kind'] not in ('set','union'):raise ValueError('unsupported chain effect')
    if set(values)!=set(range(len(rule['slots']))):raise ValueError('incomplete Cell result layout')
    return [values[i] for i in range(len(rule['slots']))]


def code(rule,values,ref):
    roles,_=template(rule)
    return encode([(i,ref.scalar_values.get(v,{}),(rule['slots'][i]['sort']['name'],ref.root(v)) if rule['slots'][i]['sort']['kind']=='eq' else None) for i,v in enumerate(values)],roles,'class-balanced')


def candidate_contexts(base,consumer,exports):
    """Independent second-entry facts; never change the prior producer state."""
    for (table,values),ports in exports.items():
        for atom in consumer['query']:
            if atom['call']['table']!=table or len(atom['args'])!=len(values):continue
            binding={};consistent=True
            for arg,value in zip(atom['args'],values):
                slot=arg['slot']
                if slot in binding and binding[slot]!=value:consistent=False
                binding[slot]=value
            if not consistent:continue
            ref=deepcopy(base)
            for slot,desc in enumerate(consumer['slots']):
                if desc['definition']!='query' or slot in binding:continue
                sort=desc['sort'];i=len(ref.parent);ref.parent.append(i);binding[slot]=i
                if sort['kind']=='eq':ref.types.append(sort['name'])
                else:
                    from device_snapshot_import import identity
                    value=dict(sort=sort['name'],value=0 if sort['kind']=='i64' else 'boundary')
                    key=identity(value)
                    if key in ref.scalar_ids:
                        ref.parent.pop();binding[slot]=ref.scalar_ids[key]
                    else:ref.types.append(None);ref.scalar_ids[key]=i;ref.scalar_values[i]=value
            for query in consumer['query']:
                vs=[binding[a['slot']] for a in query['args']]
                ref.construct(query['call']['table'],vs[:-1],vs[-1])
            ref.close()
            if any(ref.root(i)!=base.root(i) for i in range(len(base.parent))):continue
            yield ref,{slot:ref.root(v) for slot,v in binding.items()}


def pack_sources(sources,owners,ref,atoms):
    tokens=np.zeros((atoms,128),np.float32);edge=np.zeros((atoms,atoms,64),np.float32);mask=np.zeros(atoms,bool);replace=np.zeros(atoms,bool)
    for ai,(source,vals) in enumerate(sources):tokens[ai]=code(source,vals,ref);mask[ai]=True;replace[ai]=owners[ai]
    for ai,(source,vals) in enumerate(sources):
        ar,_=template(source)
        for bi,(other,vs) in enumerate(sources):
            br,_=template(other)
            terms=[ar[i]*br[j] for i,v in enumerate(vals) for j,w in enumerate(vs) if source['slots'][i]['sort']==other['slots'][j]['sort'] and ref.root(v)==ref.root(w)]
            if terms:edge[ai,bi]=np.sum(terms,axis=0)/np.sqrt(len(terms))
    return dict(tokens=tokens,edges=edge,mask=mask,replace=replace)


def chains(recipe,records,limit_per_consumer=2):
    atoms=max(len(r['query']) for r in recipe['rules']);width=max(len(r['slots']) for r in recipe['rules']);items=[];coverage=set()
    for record in records:
        producer=record['rule'];rule=recipe['rules'][producer];ref=record['reference'];values=completed(rule,record['binding'],ref)
        np.testing.assert_allclose(code(rule,values,ref),record['target'],atol=2e-6)
        exports={}
        for op in rule['effects']:
            if op['kind'] not in ('construct','set'):continue
            ports=[a['slot'] for a in op['args']]+[op['dst'] if op['kind']=='construct' else op['value']['slot']]
            exports[(op['call']['table'],tuple(values[s] for s in ports))]=ports
        if record.get('eq_changed',False):
            for atom in rule['query']:
                ports=[a['slot'] for a in atom['args']]
                exports[(atom['call']['table'],tuple(values[s] for s in ports))]=ports
        for rid,consumer in enumerate(recipe['rules']):
            accepted=0
            for ref,binding in candidate_contexts(record['reference'],consumer,exports):
                sources=[];owners=[];projections=[]
                for atom in consumer['query']:
                    row=[binding[a['slot']] for a in atom['args']];key=(atom['call']['table'],tuple(row));ports=exports.get(key)
                    if ports is not None:
                        sources.append((rule,values));owners.append(True)
                        mapping={a['slot']:p for a,p in zip(atom['args'],ports)}
                        inputs=[i for i,s in enumerate(consumer['slots']) if s['definition']=='query']
                        projections.append(compile_transfer(recipe,dict(producer=producer,consumer=rid,projection=[mapping.get(i,0) for i in inputs],projection_valid=[i in mapping for i in inputs]),width))
                    else:
                        schema=next(t['schema'] for t in recipe['tables'] if t['name']==key[0])
                        seed_rule=dict(slots=[dict(sort=s,definition='query') for s in schema],query=[dict(call=atom['call'],args=[dict(slot=i) for i in range(len(schema))])],effects=[])
                        sources.append((seed_rule,row));owners.append(False)
                if not any(owners):continue
                packed=pack_sources(sources,owners,ref,atoms)
                after=deepcopy(ref);apply_instance(after,consumer,binding);target=code(consumer,completed(consumer,binding,after),after)
                items.append(dict(parent=record['index'],producer=producer,consumer=rid,**packed,request=template(consumer)[1],target=target,valid=True,owner_covered=any(p['covered'] for p in projections)))
                # Independent, well-typed boundary fact breaks a cross-atom
                # binding while retaining at least one actual generated source.
                for ai,atom in enumerate(consumer['query']):
                    other_slots={a['slot'] for bi,q in enumerate(consumer['query']) if bi!=ai for a in q['args']}
                    if not any(a['slot'] in other_slots for a in atom['args']) or not any(owners[bi] for bi in range(len(owners)) if bi!=ai):continue
                    nr=deepcopy(ref);schema=next(t['schema'] for t in recipe['tables'] if t['name']==atom['call']['table']);fresh=[]
                    for sort in schema:
                        i=len(nr.parent);nr.parent.append(i);fresh.append(i)
                        if sort['kind']=='eq':nr.types.append(sort['name'])
                        else:
                            from device_snapshot_import import identity
                            value=dict(sort=sort['name'],value=1000+i if sort['kind']=='i64' else 'negative-'+str(i))
                            nr.types.append(None);nr.scalar_values[i]=value;nr.scalar_ids[identity(value)]=i
                    nr.construct(atom['call']['table'],fresh[:-1],fresh[-1]);nr.close()
                    if any(nr.root(i)!=ref.root(i) for i in range(len(ref.parent))):continue
                    seen={};agrees=True
                    for bi,query in enumerate(consumer['query']):
                        row=fresh if bi==ai else [binding[a['slot']] for a in query['args']]
                        for arg,v in zip(query['args'],row):
                            slot=arg['slot'];value=nr.root(v)
                            if slot in seen and seen[slot]!=value:agrees=False
                            seen[slot]=value
                    if agrees:continue  # E.g. nullary constructors cannot gain a fresh unequal result.
                    seed_rule=dict(slots=[dict(sort=t,definition='query') for t in schema],query=[dict(call=atom['call'],args=[dict(slot=i) for i in range(len(schema))])],effects=[])
                    ns=list(sources);ns[ai]=(seed_rule,fresh);no=list(owners);no[ai]=False
                    items.append(dict(parent=record['index'],producer=producer,consumer=rid,**pack_sources(ns,no,nr,atoms),request=template(consumer)[1],target=np.zeros(128,np.float32),valid=False,owner_covered=False))
                    break
                coverage.add((producer,rid));accepted+=1
                if accepted>=limit_per_consumer:break
    if not items:raise ValueError('no effect-backed chains')
    return {key:np.array([i[key] for i in items]) for key in items[0]},dict(chains=len(items),positive=sum(i['valid'] for i in items),negative=sum(not i['valid'] for i in items),negative_unavailable=sum(i['valid'] for i in items)-sum(not i['valid'] for i in items),producer_consumer_pairs=len(coverage),producers=sorted({p for p,_ in coverage}),consumers=sorted({c for _,c in coverage}),compiled_owner_opportunities=sum(i['owner_covered'] for i in items),scope='bounded effect-backed positive and mismatched-entry two-step tuples; not complete interaction enumeration or runtime ownership acceptance')

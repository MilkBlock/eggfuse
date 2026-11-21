"""Typed root/port checks and post-discovery joins to independent ordinary donor receipts."""
import json

def verify_seeds(initial,meta,seed,program):
    vals=initial['values'];ports=initial['ports'];rows=initial['rows'];hidden=set(initial.get('subsumed_rows',[]));by_table={t['name']:t for t in program['recipe']['tables']}
    classes={};seen={};out=[]
    for atom in seed['rows']:
        i=atom['atom'];table=by_table[atom['table']];args=[ports[f'input_{i}_c{c}'] for c in range(len(atom['values'])-1)]
        result=ports[f'input_{i}']
        hits=[j for j,r in enumerate(rows) if j not in hidden and r=={'op':atom['table'],'args':args,'result':result}]
        if len(hits)!=1:raise ValueError('visible seed root missing or ambiguous')
        for idx,value,ty in zip([*args,result],atom['values'],table['schema']):
            if vals[idx]['sort']!=ty['name']:raise ValueError('seed port sort differs')
            if 'Eq'in value:
                identity=(ty['name'],value['Eq'])
                if classes.setdefault(identity,idx)!=idx or seen.setdefault(idx,identity)!=identity:raise ValueError('donor seed equality partition differs')
            elif 'Int'in value or 'Text'in value:
                literal=(json.dumps(value['Text'],ensure_ascii=False) if 'Text'in value else
                         ('true' if value['Int'] else 'false') if ty['name']=='bool' else str(value['Int']))
                if vals[idx]['literal']!=literal:raise ValueError('donor seed primitive value differs')
            else:raise ValueError('unsupported seed primitive representation')
        out.append(dict(source_atom=i,table=atom['table'],source_witness=atom['named'],initial_row=hits[0],argument_classes=args,result_class=result))
    return out


def extend(item,sample,meta,program,data,initial,final,calculate):
    proof=item.get('port_binding',{});extra=[]
    if initial:
        seed=sample['consumer'] if meta['scope_mode']=='consumer' else sample['producer']
        item['seed_roots']=verify_seeds(initial,meta,seed,program)
    else:
        item['seed_roots']=[]
    for edge in proof.get('local_causal_edges',[]):
        if edge['producer_rule'] is None or edge['consumer_rule'] is None:continue
        producer=sample['producer']
        if edge['producer_rule']!=producer['rule']:continue
        # The full donor recipe may contain additional compiler-generated instructions.
        # Recover the index only from the original producer's actual named input-port state.
        rid=edge['producer_rule'];cid=edge['consumer_rule'];rule=program['recipe']['rules'][rid];consumer=program['recipe']['rules'][cid]
        fact=final['rows'][edge['row']];op=fact['op']
        possible=[]
        for i,e in enumerate(rule['effects']):
            if e.get('call',{}).get('table')!=op:continue
            try:match=calculate(final,producer,rule,i)==edge['row']
            except (IndexError,KeyError,StopIteration,ValueError):continue
            if match:possible.append(i)
        positions=[i for i,a in enumerate(consumer['query']) if a['call'].get('table')==op]
        mapped=dict(local=edge,operator=op,argument_classes=fact['args'],result_class=fact['result'],
                    compatible_producer_ops=possible,compatible_consumer_atoms=positions)
        if len(possible)==len(positions)==1:
            oi=possible[0];atom=positions[0];mapped.update(producer_op=oi,consumer_atom=atom,producer_operation=rule['effects'][oi]['op'])
            key=','.join(map(str,(rid,oi,cid,atom)))
            same=[e for e in data['neighbor_evidence'].get(str(producer['serial']),[]) if e['producer_op']==oi and e['consumer_rule']==cid and e['consumer_atom']==atom]
            receipt=same[0] if same else data['route_receipts'].get(key)
            mapped.update(donor_receipt=receipt,donor_join='same_producer' if same else 'other_producer' if receipt else 'not_observed',
                          nominated=(rid,oi,cid,atom)==(item['producer_rule'],item['producer_op'],item['consumer_rule'],item['consumer_atom']))
        extra.append(mapped)
    item['mapped_native_edges']=extra

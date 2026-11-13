"""Audit actual state growth before designing variable-size token storage.
Counts are materialized reference costs, not entropy or a token lower bound.
"""
import argparse, collections, hashlib, json, math
from pathlib import Path


def summarize(graph, width):
    scalars=[];refs=0;rows=graph['rows'];tables=collections.Counter()
    for row in rows:
        tables[row['table']]+=1
        for v in row['values']:
            if 'eq' in v:refs+=1
            elif v.get('sort')=='i64' and type(v.get('value'))==int:scalars.append(v['value'])
            else:raise ValueError(f'unsupported exact payload {v}')
    # No conversion of IDs into floating features. Scalar equality is not an
    # alias proof: occurrences remain distinct even when their values coincide.
    assert all(abs(v)<=2**24 for v in scalars), 'f32 exact integer domain exceeded'
    return dict(rows=len(rows),scalar_occurrences=len(scalars),distinct_scalar_values=len(set(scalars)),
                reference_occurrences=refs,scalar_only_blocks=math.ceil(len(scalars)/width),
                scalar_only_padding=(-len(scalars))%width,
                tables=dict(tables),visible_rows=sum(not r['subsumed'] for r in rows))


def audit(raw,width):
    records=[];growth=collections.Counter();max_blocks=0
    for c in raw['cases']:
        assert c['fixed_point']['status']=='pass'
        sequence=[c['initial']]+[b['graph'] for b in c['boundaries']]
        states=[summarize(g,width) for g in sequence]
        assert states[-1]==summarize(c['final'],width)
        seen_values={v['value'] for r in sequence[0]['rows'] for v in r['values'] if 'value' in v}
        for i,(before,after) in enumerate(zip(states,states[1:])):
            growth['transitions']+=1
            growth['row_growth']+=after['rows']>before['rows']
            growth['scalar_occurrence_growth']+=after['scalar_occurrences']>before['scalar_occurrences']
            growth['scalar_block_growth']+=after['scalar_only_blocks']>before['scalar_only_blocks']
            values={v['value'] for r in sequence[i+1]['rows'] for v in r['values'] if 'value' in v}
            growth['new_numeric_values']+=bool(values-seen_values)
            seen_values |= values
        max_blocks=max(max_blocks,max(s['scalar_only_blocks'] for s in states))
        records.append(dict(id=c['id'],source_sha256=c['source_sha256'],states=states))
    all_states=[s for r in records for s in r['states']]
    assert sum(s['scalar_occurrences']+s['scalar_only_padding'] for s in all_states)==sum(s['scalar_only_blocks']*width for s in all_states)
    logical=sum(s['scalar_occurrences'] for s in all_states)
    bucketed=sum(s['scalar_only_blocks']*width for s in all_states)
    return dict(scope='Exact saved-state capacity audit; full materialization reference, not proposed runtime storage',
        block_width=width,cases=len(records),state_snapshots=len(all_states),transitions=dict(growth),
        scalar_occurrences=logical,block_capacity_slots=bucketed,global_max_capacity_slots=len(all_states)*max_blocks*width,
        scalar_block_padding_fraction=(bucketed-logical)/bucketed,
        min_scalar_blocks=min(s['scalar_only_blocks'] for s in all_states),max_scalar_blocks=max_blocks,
        reference_occurrences=sum(s['reference_occurrences'] for s in all_states),
        limitations=['scalar-only capacity excludes topology, identity, validity and model hidden state',
        'distinct scalar values are not independent information or entropy',
        'actual intermediate snapshots are teacher evidence, not runtime-accessible input',
        'does not authorize data-dependent allocation, skip publication, or establish GPU speedup'],records=records)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--width',type=int,default=32);a=p.parse_args()
    if a.width<=0:raise ValueError('positive token width required')
    result=audit(json.loads(a.runtime.read_text()),a.width)
    result['runtime_sha256']=hashlib.sha256(a.runtime.read_bytes()).hexdigest()
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='records'},indent=2))

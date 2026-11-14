"""Rule-derived constructor-result contexts, before any completion labels."""
import argparse,json
from pathlib import Path
from synthetic_cell_inputs import generate,digest,oracle
from device_snapshot_import import identity
from reference_union_family import Reference


def result_context(recipe,snapshot,rid,mode):
    if mode not in ('absent','equal','distinct'):raise ValueError('result context mode')
    ids={}
    for row in snapshot['rows']:
        for v in row['values']:ids.setdefault(identity(v),len(ids))
    ref=Reference(recipe,snapshot['rows'],ids);rule=recipe['rules'][rid];matches=ref.matches(rule)
    if not matches:raise ValueError('no entry for selected rule')
    slots=dict(matches[0]);terminal=None
    for i,op in enumerate(rule['effects']):
        if op['kind']=='copy':slots[op['dst']]=slots[op['arg']['slot']]
        elif op['kind']=='construct':slots[op['dst']]=ref.construct(op['call']['table'],[slots[a['slot']] for a in op['args']])
        elif op['kind']=='set' and i==len(rule['effects'])-1:terminal=op
        else:raise ValueError('unsupported effect before terminal constructor Set')
    if terminal is None:raise ValueError('terminal Set required')
    table=terminal['call']['table'];args=tuple(ref.root(slots[a['slot']]) for a in terminal['args']);wanted=ref.root(slots[terminal['value']['slot']])
    if any(t==table and tuple(ref.root(v) for v in vs[:-1])==args for t,vs in ref.facts):raise ValueError('selected key already present in base')
    actual=None
    if mode!='absent':
        actual=ref.construct(table,args,wanted if mode=='equal' else None)
    ref.close()
    values={i:json.loads(v) for v,i in ids.items()}
    for i in range(len(ids),len(ref.parent)):values[i]=dict(sort=ref.types[i],eq='synthetic-result-'+str(i))
    rows=[dict(table=t,values=[values[ref.root(v)] for v in vs],subsumed=False) for t,vs in sorted(ref.normalized_facts())]
    evidence=dict(table=table,key=[values[v] for v in args],wanted=values[ref.root(wanted)],
        actual=None if actual is None else values[ref.root(actual)],already_equal=actual is not None and ref.root(actual)==ref.root(wanted))
    return dict(rows=rows),evidence


def main():
    p=argparse.ArgumentParser();p.add_argument('recipe',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    recipe=json.loads(a.recipe.read_text());a.output.mkdir(parents=True,exist_ok=True);records=[]
    # First seed from 20261200 onward with both constructor-write entries; no labels used.
    seed=20261203;base=generate(recipe,seed,4,0.)
    for rid in (1,2):
        for mode in ('absent','equal','distinct'):
            name=str(rid)+'-'+mode;snapshot,evidence=result_context(recipe,base,rid,mode)
            doc=dict(schema='synthetic-cell-input/v1',recipe=recipe,snapshot=snapshot,recipe_sha256=digest(recipe),input_sha256=digest(snapshot),
                generator=dict(seed=seed,fragments=4,reuse=0.,result_context=dict(rule=rid,mode=mode)),source='rule definitions only; result context',reachability='rule-valid; source-program reachability unproved')
            (a.output/(name+'.json')).write_text(json.dumps(doc,indent=2)+'\n')
            label=oracle(recipe,snapshot);(a.output/(name+'.label.json')).write_text(json.dumps(label,indent=2)+'\n')
            records.append(dict(case=name,status='complete',evidence=evidence,runs=label['runs'],input_sha256=doc['input_sha256']))
    (a.output/'manifest.json').write_text(json.dumps(dict(records=records),indent=2)+'\n')
    print(json.dumps(records,indent=2))

if __name__=='__main__':main()

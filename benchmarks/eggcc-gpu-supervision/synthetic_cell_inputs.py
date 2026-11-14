"""Rule-derived local inputs; no program Run, binding or target is sampled.

These inputs are valid for the selected constructor rules, not proven reachable
from an Eggcc source program. Oracle completion is separate from seed creation.
"""
import argparse, hashlib, json, random
from pathlib import Path
from device_snapshot_import import identity
from reference_union_family import Reference
from typed_literal import value as literal_value


def digest(value):return hashlib.sha256(identity(value).encode()).hexdigest()


def select_recipe(source, rules):
    selected=[source['rules'][i] for i in rules]
    names={a['call']['table'] for r in selected for a in r['query']}
    names.update(o['call']['table'] for r in selected for o in r['effects'] if 'call' in o)
    tables=[t for t in source['tables'] if t['name'] in names]
    if len(tables)!=len(names) or any(t['kind']!='constructor' for t in tables):raise ValueError('constructor family required')
    return dict(tables=tables,rules=selected)


def generate(recipe, seed, fragments=4, reuse=.35):
    if fragments<1 or not 0<=reuse<=1:raise ValueError('generation bounds')
    rng=random.Random(seed);pool={};rows=[];serial=0
    for _ in range(fragments):
        rule=rng.choice(recipe['rules']);bindings={}
        for atom in rule['query']:
            if 'table' not in atom['call']:raise ValueError('unsupported primitive query')
            values=[]
            for arg in atom['args']:
                if 'slot' not in arg:
                    values.append(literal_value(arg));continue
                slot=arg['slot'];sort=rule['slots'][slot]['sort'];name=sort['name']
                if slot not in bindings:
                    if sort['kind']=='eq':
                        choices=pool.setdefault(name,[])
                        if choices and rng.random()<reuse:value=rng.choice(choices)
                        else:
                            value=dict(sort=name,eq=str(serial));serial+=1;choices.append(value)
                    elif sort['kind']=='i64':value=dict(sort=name,value=rng.choice([-1,0,1,2,3,7]))
                    else:raise ValueError('unsupported scalar generator: '+name)
                    bindings[slot]=value
                values.append(bindings[slot])
            rows.append(dict(table=atom['call']['table'],values=values,subsumed=False))
    return canonical_seed(recipe,rows)


def canonical_seed(recipe,rows):
    # Constructor congruence is a validity condition of the seed, not a label.
    ids={identity(v):i for i,v in enumerate({identity(v):v for r in rows for v in r['values']}.values())}
    ref=Reference(recipe,[],ids)
    for row in rows:
        values=[ids[identity(v)] for v in row['values']]
        ref.construct(row['table'],values[:-1],values[-1])
    ref.close();values={i:json.loads(v) for v,i in ids.items()}
    normalized=[dict(table=t,values=[values[ref.root(i)] for i in vs],subsumed=False) for t,vs in sorted(ref.normalized_facts())]
    # All used identities remain actual typed constructor inputs/results.
    return dict(rows=normalized)


def merge_input(recipe,snapshot,left,right):
    if left==right or left.get('sort')!=right.get('sort') or 'eq' not in left or 'eq' not in right:
        raise ValueError('distinct same-sort Eq ports required')
    used={identity(v) for row in snapshot['rows'] for v in row['values']}
    if identity(left) not in used or identity(right) not in used:raise ValueError('unknown merge port')
    rows=[dict(row,values=[left if v==right else v for v in row['values']]) for row in snapshot['rows']]
    return canonical_seed(recipe,rows)


def oracle(recipe,snapshot,budget=64):
    ids={}
    for row in snapshot['rows']:
        for v in row['values']:ids.setdefault(identity(v),len(ids))
    ref=Reference(recipe,snapshot['rows'],ids)
    runs=ref.saturate(recipe['rules'],budget)
    return dict(runs=runs,initial_ids=len(ids),final_ids=len(ref.parent),unions=ref.unions,
                facts=[[t,list(v)] for t,v in sorted(ref.normalized_facts())],partition=ref.partition())


def validate(document):
    if document.get('schema')!='synthetic-cell-input/v1':raise ValueError('synthetic schema')
    if digest(document['recipe'])!=document['recipe_sha256'] or digest(document['snapshot'])!=document['input_sha256']:raise ValueError('synthetic provenance')
    g=document['generator']
    expected=generate(document['recipe'],g['seed'],g['fragments'],g['reuse'])
    if 'initial_merge' in g:expected=merge_input(document['recipe'],expected,*g['initial_merge'])
    if 'result_context' in g:
        from synthetic_result_ownership import result_context
        c=g['result_context'];expected,_=result_context(document['recipe'],expected,c['rule'],c['mode'])
    if expected!=document['snapshot']:raise ValueError('seed replay mismatch')
    return document['recipe'],document['snapshot']


def main():
    p=argparse.ArgumentParser();p.add_argument('recipe',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--rules',default='283,290,293');p.add_argument('--seed',type=int,default=20261120);p.add_argument('--count',type=int,default=12);p.add_argument('--fragments',type=int,default=4);a=p.parse_args()
    if a.count<1:raise ValueError('positive count')
    source=json.loads(a.recipe.read_text());recipe=select_recipe(source.get('recipe',source),list(map(int,a.rules.split(','))))
    a.output.mkdir(parents=True,exist_ok=True);records=[]
    for seed in range(a.seed,a.seed+a.count):
        snapshot=generate(recipe,seed,a.fragments)
        doc=dict(schema='synthetic-cell-input/v1',recipe=recipe,snapshot=snapshot,recipe_sha256=digest(recipe),input_sha256=digest(snapshot),
                 generator=dict(seed=seed,fragments=a.fragments,reuse=.35),source='rule definitions only; no real Run samples',reachability='rule-valid; source-program reachability unproved')
        path=a.output/(str(seed)+'.json');path.write_text(json.dumps(doc,indent=2)+'\n')
        try:label=oracle(recipe,snapshot)
        except ValueError as e:records.append(dict(seed=seed,status='rejected',reason=str(e)));continue
        path.with_suffix('.label.json').write_text(json.dumps(label,indent=2)+'\n')
        records.append(dict(seed=seed,status='complete',input_sha256=doc['input_sha256'],rows=len(snapshot['rows']),runs=len(label['runs']),unions=label['unions'],applications=sum(r['applications'] for r in label['runs'])))
    report=dict(scope='synthetic local constructor family; not full Eggcc',training_performed=False,backpropagation=False,records=records)
    (a.output/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()

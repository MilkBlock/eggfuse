"""Rule-derived wrapper/projection inputs with controlled irrelevant neighbors.

No observed graph, binding, scalar or label is consumed. This bounded family
requires a two-atom projection -> wrapper query; it is not all Cell interactions.
"""
import argparse,itertools,json
from pathlib import Path
from synthetic_cell_inputs import canonical_seed,digest,select_recipe


def generate(recipe,rule,variant,neighbors,scalar):
    if type(rule)is not int or not 0<=rule<len(recipe['rules']):raise ValueError('rule index')
    if variant not in ('linked','other_context','other_result','absent'):raise ValueError('context variant')
    if type(neighbors)is not int or neighbors<0:raise ValueError('neighbor count')
    if type(scalar)is not int or not -(2**63)<=scalar<2**63:raise ValueError('i64 scalar')
    r=recipe['rules'][rule];q=r['query'];tables={t['name']:t for t in recipe['tables']}
    if len(q)!=2 or any(len(a['args'])!=3 or any('slot' not in x for x in a['args']) for a in q):raise ValueError('two ternary constructor atoms required')
    a,index,result=[x['slot'] for x in q[0]['args']];ctx,inner,out=[x['slot'] for x in q[1]['args']]
    if inner!=result or len({a,index,result,ctx,out})!=5:raise ValueError('projection-wrapper wiring required')
    kinds=[r['slots'][s]['sort']['kind'] for s in (a,index,result,ctx,out)]
    if kinds!=['eq','i64','eq','eq','eq']:raise ValueError('projection-wrapper types')
    expr=r['slots'][a]['sort'];context=r['slots'][ctx]['sort']
    if any(r['slots'][s]['sort']!=expr for s in (result,out)):raise ValueError('wrapper must preserve expression type')
    for atom in q:
        t=tables[atom['call']['table']]
        if t['kind']!='constructor' or t['schema']!=[r['slots'][x['slot']]['sort'] for x in atom['args']]:raise ValueError('constructor schema mismatch')
    eq=lambda sort,name:dict(sort=sort['name'],eq=name)
    values={a:eq(expr,'input'),index:dict(sort=r['slots'][index]['sort']['name'],value=scalar),result:eq(expr,'projected'),ctx:eq(context,'context'),out:eq(expr,'wrapped')}
    rows=[dict(table=atom['call']['table'],values=[values[x['slot']] for x in atom['args']],subsumed=False) for atom in q]
    wrapper=q[1]['call']['table']
    if variant!='absent':
        rows.append(dict(table=wrapper,values=[eq(context,'other-context') if variant=='other_context' else values[ctx],eq(expr,'parent'),eq(expr,'other-result') if variant=='other_result' else values[a]],subsumed=False))
    for i in range(neighbors):
        rows.append(dict(table=wrapper,values=[values[ctx],eq(expr,'distractor-input-'+str(i)),eq(expr,'distractor-output-'+str(i))],subsumed=False))
    return canonical_seed(recipe,rows)


def document(recipe,rule,variant,neighbors,scalar):
    g=dict(kind='context-density/v1',rule=rule,variant=variant,neighbors=neighbors,scalar=scalar)
    snapshot=generate(recipe,rule,variant,neighbors,scalar)
    return dict(schema='synthetic-cell-input/v1',recipe=recipe,recipe_sha256=digest(recipe),snapshot=snapshot,input_sha256=digest(snapshot),generator=g,source='rule definitions only',reachability='rule-valid open constructor boundary; source-program reachability unproved')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('recipe',type=Path);p.add_argument('output',type=Path);p.add_argument('--rules',default='0,1,2');p.add_argument('--rule',type=int,default=1);p.add_argument('--neighbors',default='0,4,12');p.add_argument('--scalars',default='0,3');a=p.parse_args()
    raw=json.loads(a.recipe.read_text());recipe=select_recipe(raw.get('recipe',raw),list(map(int,a.rules.split(','))))
    docs=[document(recipe,a.rule,v,n,s) for v,n,s in itertools.product(('linked','other_context','other_result','absent'),map(int,a.neighbors.split(',')),map(int,a.scalars.split(',')))]
    a.output.mkdir(parents=True,exist_ok=False)
    (a.output/'documents.jsonl').write_text(''.join(json.dumps(d)+'\n' for d in docs))
    (a.output/'manifest.json').write_text(json.dumps(dict(input_format='documents',recipe=recipe,recipe_sha256=digest(recipe),inputs=len(docs),training_performed=False,scope='bounded synthetic wrapper/projection context density'),indent=2)+'\n')
    print(len(docs))

"""Replay the external and independent-instance control using actual ordered Runs."""
import argparse
import json
from pathlib import Path

from export import HERE, require, term_values
from replays import minimal_case


def build_cases(program,templates):
    cases=[]
    for t in templates:
        rid=t['provenance']['sum-bits']['rule'];source_set=program['recipe']['rules'][rid]['metadata']['source_set']
        cert,=t['certificates'];p,q=cert['left_port'],cert['right_port'];r,=set(t['public_ports'])-{p,q}
        base=minimal_case(program,rid)
        # Split the generated fixture after its fixed helper rule. Stage all of the
        # first instance's facts in a separate ruleset for the lagging-owner case.
        decl,facts=base['source'].split('(rule ((Observe i v) (Want j v)) ((Seen i j)) :ruleset observe)\n')
        decl+='(rule ((Observe i v) (Want j v)) ((Seen i j)) :ruleset observe)\n'
        body=facts[:facts.index('(run-schedule')].splitlines()
        boundary=next(i+1 for i,x in enumerate(body) if x.startswith('(Want 0 '))
        def add(kind,text,**kwargs):
            meta=dict(base['metadata'],mode=kind,public=t['public_ports'],**kwargs)
            cases.append(dict(base,id=f'r{rid}-{kind}',source=text,metadata=meta))
        delayed=['(ruleset reveal)', '(relation Trigger ())', '(Trigger)',
                 '(rule ((Trigger)) ('+' '.join(body[:boundary])+') :ruleset reveal)', *body[boundary:],
                 f'(run-schedule (seq (run {source_set}) (run reveal) (run observe)))']
        add('only-second',decl+'\n'.join(delayed)+'\n')
        roles={'p':p,'q':q,'r':r}
        pairs=[(i+j,(roles[i],roles[j])) for i in roles for j in roles]
        for name,(x,y) in pairs:
            a,b=x,16+y
            ext=['(ruleset external)',f'(rule ((Observe {a} x) (Observe {b} y)) ((union x y)) :ruleset external)',
                 *body,f'(run-schedule (seq (run {source_set}) (run external) (run observe)))']
            add('external-'+name,decl+'\n'.join(ext)+'\n',external=[a,b])
    return {'cases':cases}


def close_external(record, first, ids, a, b):
    """Apply an external union, then close actual same-table constructor signatures."""
    parent={}
    def root(x):
        parent.setdefault(x,x)
        while x!=parent[x]:x=parent[x]
        return x
    def unite(x,y):
        x,y=root(x),root(y)
        if x==y:return False
        parent[x]=y;return True
    def eq(v): return (v['sort'],v['eq'])
    sort=record['metadata']['ports'][0]['sort']
    cell=lambda i:(sort,first[i])
    unite(cell(a), cell(b))
    recipe=record['compiled_program']['recipe']
    names={t['name'] for t in recipe['tables'] if t['kind']=='constructor'}
    rows=[row for row in record['boundaries'][0]['graph']['rows']
          if row['table'] in names and not row['subsumed']]
    changed=True
    while changed:
        signatures={};changed=False
        for row in rows:
            *args,result=row['values']
            if 'eq' not in result:continue
            key=(row['table'],tuple(root(eq(v)) if 'eq' in v else (v['sort'],v['value']) for v in args))
            if key in signatures:changed |= unite(eq(result),signatures[key])
            else:signatures[key]=eq(result)
    return {(i,j) for i in ids for j in ids if root(cell(i))==root(cell(j))}


def verify(record):
    meta=record['metadata'];p,q=meta['pair'];public=meta['public']
    ids=[p+16*i for i in (0,1) for p in public]; steps=record['steps']
    baseline,_=term_values(record['initial']);first,_=term_values(record['boundaries'][0]['graph']);mid,_=term_values(record['boundaries'][1]['graph']);post,seen=term_values(record['boundaries'][2]['graph'])
    require(post==mid, 'read-only observer altered class membership')
    parent={i:i for i in ids}
    def root(x):
        while x!=parent[x]:x=parent[x]
        return x
    def unite(x,y):parent[root(x)]=root(y)
    def check(values,selected):
        for i in selected:
            for j in selected:
                require((values[i]==values[j])==(root(i)==root(j)),f"{record['id']}: unexpected equivalence {i},{j}")
    delayed=meta['mode']=='only-second';initial=[i for i in ids if i>=16] if delayed else ids
    check(baseline,initial);require(steps[0]['logical_matches']==(1 if delayed else 2),'wrong producer executions')
    unite(p+16,q+16)
    if not delayed:unite(p,q)
    check(first,initial)
    secondary=[]
    if not delayed:
        require(steps[1]['ruleset']=='external' and steps[1]['logical_matches']==1,'external effect not executed')
        a,b=meta['external'];require(root(a)!=root(b),'ineffective external union');unite(a,b)
        for i,j in sorted(close_external(record,first,ids,a,b)):
            if root(i)!=root(j):
                secondary.append([i,j]);unite(i,j)
    else:require(steps[1]['ruleset']=='reveal','first owner must become visible after producer Run')
    check(post,ids)
    require({(i,j) for i,j in seen if i in ids}=={(i,j) for i in ids for j in (0,1) if root(i)==root(16*j+q)},'unexpected consumer observations')
    return dict(id=record['id'],source_sha256=record['source_sha256'],program_sha256=record['program_sha256'],
                runs=[dict(ruleset=s['ruleset'],matches=s['logical_matches']) for s in steps],
                external_endpoints=meta.get('external'), secondary_congruence=secondary,
                equal_groups=sorted({tuple(i for i in ids if root(i)==root(j)) for j in ids}),
                consumer_reads=sorted((i,j) for i,j in seen if i in ids))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('build','verify'));parser.add_argument('source',type=Path);parser.add_argument('output',type=Path);args=parser.parse_args()
    source=json.loads(args.source.read_text());templates=json.loads((HERE/'manifest.json').read_text())['templates']
    if args.mode=='build':result=build_cases(source,templates)
    else:
        records=[verify(c) for c in source['cases']];require(len(records)==len(templates)*10,'missing event cases');result=dict(status='pass',cases=records)
    args.output.write_text(json.dumps(result,indent=1)+'\n');print('cases',len(result['cases']))


if __name__=='__main__':main()

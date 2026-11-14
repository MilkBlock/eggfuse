"""Finite total constructor models for boundary non-equality certificates.

Only positive constructor queries, copy/construct/set/union, Eq sorts and i64
are supported. This proves boundary distinctions, not absence of future facts.
"""
import itertools
from synthetic_cell_inputs import validate
from reference_union_family import Reference
from device_snapshot_import import identity
from typed_literal import value as literal


def build(document,steps=8):
    recipe,snapshot=validate(document);ids={}
    for row in snapshot['rows']:
        for v in row['values']:ids.setdefault(identity(v),len(ids))
    ref=Reference(recipe,snapshot['rows'],ids)
    for _ in range(steps):ref.apply(recipe['rules'])
    boundary=[(k,v) for k,v in ids.items() if ref.types[v] is not None]
    observed=[ref.root(v) for _,v in boundary]
    eq_sorts={s['name'] for t in recipe['tables'] for s in t['schema'] if s['kind']=='eq'}
    defaults={}
    for name in sorted(eq_sorts):
        i=len(ref.parent);ref.parent.append(i);ref.types.append(name);defaults[name]=i
    known_scalars={v['value'] for v in ref.scalar_values.values()}
    other=0
    while other in known_scalars:other+=1
    scalar_arg=dict(literal=other,sort=dict(kind='i64',name='i64'))
    other_id=ref.operand(scalar_arg,{})
    for rule in recipe['rules']:
        for atom in rule['query']:
            if 'table' not in atom['call']:raise ValueError('constructor-only query')
            for a in atom['args']:
                if 'slot' not in a:ref.operand(a,{})
    domains={name:sorted({ref.root(i) for i,t in enumerate(ref.types) if t==name}) for name in eq_sorts}
    domains['i64']=sorted(ref.scalar_values)
    for table in recipe['tables']:
        if table['kind']!='constructor' or table['schema'][-1]['kind']!='eq':raise ValueError('unsupported table')
        for key in itertools.product(*(domains[s['name']] for s in table['schema'][:-1])):
            if not any(t==table['name'] and tuple(ref.root(v) for v in vs[:-1])==key for t,vs in ref.facts):
                ref.construct(table['name'],key,defaults[table['schema'][-1]['name']])
    size=len(ref.parent)
    for _ in range(size+1):
        changed,_=ref.apply(recipe['rules'])
        if len(ref.parent)!=size:raise ValueError('model not total')
        if not changed:break
    else:raise ValueError('finite closure did not settle')
    cert=dict(domains={k:sorted({ref.root(i) for i in v}) for k,v in domains.items()},
              scalar_values={str(i):v['value'] for i,v in ref.scalar_values.items()},other_scalar=other_id,
              facts=[[t,list(v)] for t,v in sorted(ref.normalized_facts())],
              seed={k:ref.root(v) for k,v in ids.items()})
    wanted=[[observed[i]==observed[j] for j in range(len(observed))] for i in range(len(observed))]
    actual=[[cert['seed'][a]==cert['seed'][b] for b,_ in boundary] for a,_ in boundary]
    return cert,dict(boundary_exact=actual==wanted,observed_steps=steps,boundary_ports=len(boundary),model_facts=len(cert['facts']))


def verify(document,cert):
    """Check totality and every ground rule instance; never trust search success."""
    recipe,snapshot=validate(document);domains=cert['domains'];tables={t['name']:t for t in recipe['tables']};lookup={};rows={t:[] for t in tables}
    all_ids=[]
    for domain in domains.values():
        if not domain or any(type(i)is not int or i<0 for i in domain) or len(set(domain))!=len(domain):raise ValueError('invalid domain')
        all_ids.extend(domain)
    if len(set(all_ids))!=len(all_ids):raise ValueError('overlapping typed domains')
    for table in tables.values():
        if any(s['kind'] not in ('eq','i64') for s in table['schema']):raise ValueError('unsupported sort')
    for rule in recipe['rules']:
        for atom in rule['query']:
            if set(atom['call'])!={'table'}:raise ValueError('unsupported query')
            schema=tables[atom['call']['table']]['schema']
            if len(atom['args'])!=len(schema):raise ValueError('query arity')
            for a,sort in zip(atom['args'],schema):
                actual=rule['slots'][a['slot']]['sort'] if 'slot' in a else a['sort']
                if actual!=sort:raise ValueError('query type')
    scalar_values={int(i):v for i,v in cert['scalar_values'].items()}
    if set(scalar_values)!=set(domains['i64']) or cert['other_scalar'] not in scalar_values:raise ValueError('scalar domain')
    if len(set(scalar_values.values()))!=len(scalar_values):raise ValueError('duplicate scalar representatives')
    def scalar(a):
        v=literal(a)['value']
        return next((i for i,x in scalar_values.items() if x==v),cert['other_scalar'])
    for t,vs in cert['facts']:
        schema=tables[t]['schema']
        if len(vs)!=len(schema) or any(v not in domains[s['name']] for v,s in zip(vs,schema)):raise ValueError('ill-typed fact')
        key=(t,tuple(vs[:-1]))
        if key in lookup:raise ValueError('duplicate key')
        lookup[key]=vs[-1];rows[t].append(vs)
    for t,table in tables.items():
        if table['kind']!='constructor' or table['schema'][-1]['kind']!='eq':raise ValueError('unsupported table')
        for key in itertools.product(*(domains[s['name']] for s in table['schema'][:-1])):
            if (t,key) not in lookup:raise ValueError('non-total constructor')
    def operand(a,env):return env[a['slot']] if 'slot' in a else scalar(a)
    for row in snapshot['rows']:
        vals=[cert['seed'][identity(v)] for v in row['values']]
        if lookup[(row['table'],tuple(vals[:-1]))]!=vals[-1]:raise ValueError('seed not satisfied')
        for v,x in zip(row['values'],vals):
            if 'eq' not in v and scalar_values[x]!=v['value']:raise ValueError('seed scalar mismatch')
    checked=0
    for rule in recipe['rules']:
        matches=[{}]
        for atom in rule['query']:
            following=[]
            for env,vs in itertools.product(matches,rows[atom['call']['table']]):
                bound=dict(env);ok=True
                for a,v in zip(atom['args'],vs):
                    if 'slot' not in a:ok &= scalar(a)==v
                    elif a['slot'] in bound:ok &= bound[a['slot']]==v
                    else:bound[a['slot']]=v
                if ok:following.append(bound)
            matches=following
        for env in matches:
            checked+=1
            for op in rule['effects']:
                if op['kind']=='copy':env[op['dst']]=operand(op['arg'],env)
                elif op['kind']=='union':
                    if len({operand(a,env) for a in op['args']})!=1:raise ValueError('rule union violated')
                elif op['kind'] in ('construct','set'):
                    v=lookup[(op['call']['table'],tuple(operand(a,env) for a in op['args']))]
                    if op['kind']=='construct':env[op['dst']]=v
                    elif v!=operand(op['value'],env):raise ValueError('rule set violated')
                else:raise ValueError('unsupported effect')
    return dict(checked_ground_instances=checked,valid=True)


def main():
    import argparse,json,tarfile,hashlib
    from pathlib import Path
    from enumerated_boundary_labels import label
    p=argparse.ArgumentParser();p.add_argument('inputs',type=Path);p.add_argument('growth',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    sources=json.loads((a.inputs/'manifest.json').read_text());growth=json.loads((a.growth/'report.json').read_text());by_index={r['index']:r for r in sources['records']};records=[]
    def read(path,digest,member):
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('archive provenance')
        with tarfile.open(path) as t:return json.load(t.extractfile(member))
    for observed in growth['records']:
        index=observed['index'];source=by_index[index]
        document=read(a.inputs/(str(index)+'.tar.gz'),source['archive_sha256'],'case/input.json')
        trace=read(a.growth/(str(index)+'.tar.gz'),observed['archive_sha256'],'case/trace.json')
        if not observed['comparison']['passed']:raise ValueError('missing native/reference correspondence')
        native=label(document,trace);cert,status=build(document,growth['bound']);proof=verify(document,cert)
        classes={};partition=[classes.setdefault(cert['seed'][identity(v)],len(classes)) for v in native['ports']]
        exact=partition==native['partition']
        records.append(dict(index=index,input_sha256=document['input_sha256'],source_archive_sha256=source['archive_sha256'],native_archive_sha256=observed['archive_sha256'],certificate=cert,proof=proof,
                            boundary_exact=exact,native_partition=native['partition'],model_partition=partition,
                            status='boundary_eq_certified' if exact else 'inconclusive'))
    out=dict(scope='boundary Eq only: native derivations plus checked total model; no global saturation, future-constructor or retirement claim',records=records,certified=sum(r['boundary_exact'] for r in records),inconclusive=sum(not r['boundary_exact'] for r in records))
    a.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='records'}))
if __name__=='__main__':main()

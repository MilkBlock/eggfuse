"""Semantic targets for whole-Cell completion, not per-frame storage transfer.

The teacher is a bounded monotone constructor/equality interpreter over Bake
facts. A target retains every source fact under its quotient map. No executor
storage, source Run scheduling or runtime binding history is changed here.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
from cell_token_successors import compile_catalog


def freeze(x):
    return tuple(freeze(v) for v in x) if isinstance(x,(list,tuple)) else x


def compose(source,rule,binding,tables):
    """Complete a consumer inside the existing Cell and retain its whole body."""
    source=[(name,tuple(freeze(a) for a in args)) for name,args,*_ in source]
    env={int(i):freeze(v) for i,v in binding};parent={};facts=list(source)
    symbols={v for _,args in facts for v in args};symbols.update(env.values())
    def root(v):
        while v in parent:v=parent[v]
        return v
    def union(a,b):
        a,b=root(a),root(b)
        if a==b:return False
        parent[b]=a;return True
    def arg(a):
        if 'slot' in a:return env[a['slot']]
        return ('literal',json.dumps(a,sort_keys=True))
    # Verify the complete consumer precondition before applying any effect.
    for atom in rule['query']:
        name=atom['call'].get('table')
        if tables.get(name,{}).get('kind')!='constructor':return None,'unproved consumer query'
        if (name,tuple(arg(a) for a in atom['args'])) not in facts:return None,'missing consumer premise'
    for index,op in enumerate(rule['effects']):
        kind=op['kind'];name=op.get('call',{}).get('table')
        if kind=='copy':env[op['dst']]=arg(op['arg'])
        elif kind=='union':union(*[arg(a) for a in op['args']])
        elif kind in ('construct','set') and tables.get(name,{}).get('kind')=='constructor':
            values=tuple(arg(a) for a in op['args'])
            if kind=='construct':
                # Fresh local logical name, not a physical constructor address.
                value=('completion',index,0)
                while value in symbols:value=('completion',index,value[2]+1)
                symbols.add(value);env[op['dst']]=value
            else:value=arg(op['value'])
            facts.append((name,values+(value,)))
        else:return None,'unsupported effect: '+kind
    changed=True
    while changed:
        changed=False;keys={}
        for name,args in facts:
            args=tuple(root(a) for a in args);key=(name,args[:-1])
            if key in keys:changed=union(keys[key],args[-1]) or changed
            else:keys[key]=args[-1]
    target=set((name,tuple(root(a) for a in args)) for name,args in facts)
    inherited=set((name,tuple(root(a) for a in args)) for name,args in source)
    if not inherited<=target:raise AssertionError('source information lost')
    old_symbols={v for _,args in source for v in args}
    quotient={v:root(v) for v in old_symbols}
    equalities_added=len(old_symbols)-len(set(quotient.values()))
    return dict(facts=sorted(target,key=repr),source_map=sorted(quotient.items(),key=repr),
        source_facts=len(set(source)),retained_source_facts=len(inherited),new_facts=len(target-inherited),
        source_equalities_added=equalities_added,novel=bool(target-inherited) or equalities_added>0),None


def targets(recipe,catalog):
    tables={t['name']:t for t in recipe['tables']};rows=[];marks=[]
    for index,edge in enumerate(catalog['edges']):
        source=catalog['cells'][edge['producer']]
        target,reason=compose(source,recipe['rules'][edge['consumer']],edge['inputs'],tables)
        if reason:marks.append(dict(edge=index,reason=reason));continue
        rows.append(dict(edge=index,producer=edge['producer'],consumer=edge['consumer'],
            source_set=edge['source_set'],target_set=edge['target_set'],source=source,
            completion=target,source_run_validated=False))
    return dict(schema='whole-cell-completion-targets/v1',targets=rows,marks=marks,
        scope='offline semantic targets for a future GPU whole-Cell transition; no model or runtime takeover')


def main():
    p=argparse.ArgumentParser();p.add_argument('program',type=Path);p.add_argument('output',type=Path);args=p.parse_args()
    program=json.loads(args.program.read_text());catalog=compile_catalog(program['recipe']);out=targets(program['recipe'],catalog)
    out['program_sha256']=program['sha256'];args.output.write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(dict(targets=len(out['targets']),novel=sum(t['completion']['novel'] for t in out['targets']),zero_information=sum(not t['completion']['novel'] for t in out['targets']),marked=dict(Counter(m['reason'] for m in out['marks'])),retained_source_facts=sum(t['completion']['retained_source_facts'] for t in out['targets']),new_facts=sum(t['completion']['new_facts'] for t in out['targets']))))

if __name__=='__main__':main()

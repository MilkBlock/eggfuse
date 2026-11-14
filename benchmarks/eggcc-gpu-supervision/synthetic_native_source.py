"""Emit synthetic Cell inputs as native .egg programs for Eggfuse execution."""
import argparse,json,re
from pathlib import Path
from synthetic_cell_inputs import validate
from typed_literal import value as literal
from device_snapshot_import import identity


def symbol(s):
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*',s):raise ValueError('unsupported source symbol')
    return s


def control(node):
    if isinstance(node,list):return '(seq '+' '.join(map(control,node))+')'
    if set(node)=={'run'}:return '(run '+symbol(node['run'])+')'
    if set(node)=={'sequence'}:return control(node['sequence'])
    if set(node)=={'saturate'}:return '(saturate '+control(node['saturate'])+')'
    if set(node)=={'repeat','body'} and type(node['repeat']) is int and node['repeat']>=0:return '(repeat '+str(node['repeat'])+' '+control(node['body'])+')'
    raise ValueError('unsupported control')


def emit(document,schedule):
    recipe,snapshot=validate(document);tables={t['name']:t for t in recipe['tables']}
    sorts=sorted({s['name'] for t in tables.values() for s in t['schema'] if s['kind']=='eq'})
    lines=['; Synthetic structure only; private seed constructors name open Eq ports.']
    for s in sorts:
        symbol(s);seed='SyntheticSeed_'+s
        if seed in tables:raise ValueError('reserved seed constructor')
        lines.extend(['(sort '+s+')','(constructor '+seed+' (i64) '+s+')'])
    for t in tables.values():
        if t['kind']!='constructor' or t['schema'][-1]['kind']!='eq':raise ValueError('constructor-only source')
        lines.append('(constructor '+symbol(t['name'])+' ('+' '.join(symbol(s['name']) for s in t['schema'][:-1])+') '+symbol(t['schema'][-1]['name'])+')')
    stages=list(dict.fromkeys(r['metadata']['source_set'] for r in recipe['rules']))
    lines += ['(ruleset '+symbol(s)+')' for s in stages]
    def arg(a):return 'v'+str(a['slot']) if 'slot' in a else str(literal(a)['value'])
    def call(op):return '('+symbol(op['call']['table'])+(' '+' '.join(map(arg,op['args'])) if op['args'] else '')+')'
    for rule in recipe['rules']:
        query=[];effects=[]
        for atom in rule['query']:
            query.append('(= '+arg(atom['args'][-1])+' '+call(dict(atom,args=atom['args'][:-1]))+')')
        for op in rule['effects']:
            if op['kind']=='copy':effects.append('(let v'+str(op['dst'])+' '+arg(op['arg'])+')')
            elif op['kind']=='construct':effects.append('(let v'+str(op['dst'])+' '+call(op)+')')
            elif op['kind']=='set':effects.append('(union '+call(op)+' '+arg(op['value'])+')')
            elif op['kind']=='union':effects.append('(union '+' '.join(map(arg,op['args']))+')')
            else:raise ValueError('unsupported source effect')
        lines.append('(rule ('+' '.join(query)+') ('+' '.join(effects)+') :ruleset '+symbol(rule['metadata']['source_set'])+')')
    names={}
    for row in snapshot['rows']:
        for v in row['values']:
            if 'eq' in v and identity(v) not in names:
                n=len(names);names[identity(v)]='(SyntheticSeed_'+symbol(v['sort'])+' '+str(n)+')'
    def field(v):
        if 'eq' in v:return names[identity(v)]
        return str(literal(dict(literal=v['value'],sort=dict(kind=v['sort'],name=v['sort'])))['value'])
    for row in snapshot['rows']:
        if row.get('subsumed'):raise ValueError('hidden seed unsupported')
        vs=row['values'];term='('+symbol(row['table'])+(' '+' '.join(map(field,vs[:-1])) if vs[:-1] else '')+')'
        lines.append('(union '+field(vs[-1])+' '+term+')')
    lines.append('(run-schedule '+control(schedule)+')')
    return '\n'.join(lines)+'\n'


def main():
    p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('output',type=Path);p.add_argument('--schedule',type=Path);a=p.parse_args()
    document=json.loads(a.input.read_text());stages=list(dict.fromkeys(r['metadata']['source_set'] for r in document['recipe']['rules']))
    if not a.schedule and len(stages)!=1:raise ValueError('explicit multistage schedule required')
    schedule=json.loads(a.schedule.read_text()) if a.schedule else dict(saturate=dict(run=stages[0]))
    a.output.write_text(emit(document,schedule))
if __name__=='__main__':main()

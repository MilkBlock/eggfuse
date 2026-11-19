"""Offline typed ingress and plan lowering. The executable packet contains no flat fact table."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np


def canonical(value):
    return json.dumps(value,ensure_ascii=False,separators=(',',':'),sort_keys=True)


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def encode(rows,tables,*,compose=True):
    names={t['name']:i for i,t in enumerate(tables)}
    # These stable external identities refer to facts in this serialized input.
    # The record's physical origin BEFORE serialization is not available.
    ordered=sorted(rows,key=canonical)
    if len({canonical(r) for r in ordered})!=len(rows):
        raise ValueError('duplicate identical serialized facts have no distinct source handle')
    writers=defaultdict(list)
    for i,row in enumerate(ordered):
        sig=tables[names[row['table']]]['schema'];values=row['values']
        if len(sig)!=len(values) or any(v['sort']!=s['name'] for v,s in zip(values,sig)):
            raise ValueError('typed input arity/sort mismatch')
        if 'eq' in values[-1]:writers[canonical(values[-1])].append(i)
    shapes=defaultdict(list)
    for c,row in enumerate(ordered):
        links=defaultdict(list)
        for k,v in enumerate(row['values'][:-1]):
            candidates=writers.get(canonical(v),())
            if len(candidates)==1 and candidates[0]!=c:links[candidates[0]].append(k)
        for p,positions in links.items():
            shapes[ordered[p]['table'],row['table'],tuple(positions)].append((p,c))
    available=set(range(len(rows)));groups=[]
    for key in (sorted(shapes,key=lambda k:(-len(shapes[k]),k)) if compose else ()):
        for p,c in shapes[key]:
            if p in available and c in available:
                groups.append((p,c));available.difference_update((p,c))
    groups.extend((i,) for i in sorted(available));groups.sort(key=min)
    symbols=[];symbol_ids={}
    def intern(v):
        key=canonical(v)
        if key not in symbol_ids:symbol_ids[key]=len(symbols);symbols.append(v)
        return symbol_ids[key]
    templates=[];instances=[];ids={}
    for group in groups:
        members=[];params=[];positions={}
        for i in group:
            row=ordered[i];ports=[]
            for col,v in enumerate(row['values']):
                # Negative operand designates an earlier member's result CLASS.
                # It is not a claim that this edge historically read that member.
                if len(members) and col<len(row['values'])-1 and 'eq' in v and writers[canonical(v)]==[group[0]]:
                    ports.append(-1)
                else:
                    s=intern(v)
                    if s not in positions:positions[s]=len(params);params.append(s)
                    ports.append(positions[s])
            members.append([names[row['table']],ports])
        key=canonical(members)
        if key not in ids:ids[key]=len(templates);templates.append(members)
        instances.append([ids[key],params,[int(ordered[i]['subsumed']) for i in group]])
    return templates,instances,symbols


def packet(program,root,compose=True):
    r=json.loads(program.read_text());p=r['recipe'];tables=p['tables'];idx={t['name']:i for i,t in enumerate(tables)}
    templates,cells,symbols=encode(r['initial'],tables,compose=compose)
    literal={canonical(v):i for i,v in enumerate(symbols)}
    def operand(a):
        if 'slot' in a:return int(a['slot'])
        if a['sort']['kind'] not in ('String','i64','Unit','bool','f64'):raise ValueError(a)
        v={'sort':a['sort']['name'],'value':a['literal']}
        # bool and integer wire forms use the typed runtime's native representation.
        if a['sort']['kind']=='bool':v['value']=bool(v['value'])
        key=canonical(v)
        if key not in literal:literal[key]=len(symbols);symbols.append(v)
        return -1-literal[key]
    rules=[];schedule=p['control'];sets={s['name']:s['rule_ids'] for s in p['rulesets']}
    for rule in p['rules']:
        atoms=[];effects=[]
        for q in rule['query']:
            call=q['call'];atoms.append([idx[call['table']] if 'table' in call else call['primitive'],
                                          [operand(a) for a in q['args']]])
        for e in rule['effects']:
            call=e.get('call',{});args=list(e.get('args',[]))
            if 'arg' in e:args=[e['arg']]
            if 'value' in e:args.append(e['value'])
            effects.append([e['kind'],idx[call['table']] if 'table' in call else call.get('primitive',-1),
                            e.get('dst',-1),[operand(a) for a in args]])
        rules.append(dict(q=atoms,e=effects,n=len(rule['slots']),inputs=[i for i,s in enumerate(rule['slots']) if s['definition']=='query'],
                          semi=rule['metadata']['seminaive']))
    root.mkdir(parents=True,exist_ok=True)
    # Preserve the source engine's public import precedence separately from
    # the canonical Cell layout. It affects ordered commits after matching.
    rank={}
    for row in r['initial']:
        for v in row['values']:
            if 'eq' in v:rank.setdefault(canonical(v),len(rank)+1)
    eq_order=[rank.get(canonical(v),0) for v in symbols]
    result=dict(eq_order=eq_order,format='eggfuse.cell-ingress/1',tables=tables,symbols=symbols,templates=templates,instances=cells,
                sets=sets,control=schedule,rules=rules,program_sha256=digest(program),recipe_sha256=p['sha256'])
    (root/'ingress.json').write_text(canonical(result)+'\n')
    return result


def members(packet):
    """Independent decoder for replay/tests only."""
    for cell,(tid,params,hidden) in enumerate(packet['instances']):
        returned=[]
        for op,(table,ports) in enumerate(packet['templates'][tid]):
            vals=[params[i] if i>=0 else returned[-1-i] for i in ports]
            returned.append(vals[-1])
            yield cell,op,dict(table=packet['tables'][table]['name'],values=[packet['symbols'][v] for v in vals],subsumed=bool(hidden[op]))


if __name__=='__main__':
    par=argparse.ArgumentParser();par.add_argument('program',type=Path);par.add_argument('out',type=Path)
    par.add_argument('--singletons',action='store_true')
    args=par.parse_args();packet(args.program,args.out,not args.singletons)

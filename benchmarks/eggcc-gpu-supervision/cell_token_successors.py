"""Bake closed constructor Cell continuations from template operations.

No execution trace, matched binding or post-state is read. A successor requires
all consumer query atoms to be witnessed inside the completed producer Cell.
Unknown joins, mutable reads and primitive guards remain explicit boundaries.
The symbols here denote shared terms, not physical returned node addresses.
"""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path


def complete_template(rule,tables):
    env={i:('input',i) for i,s in enumerate(rule['slots']) if s['definition']=='query'}
    parent={};facts=[]
    def root(v):
        while v in parent:v=parent[v]
        return v
    def union(a,b):
        a,b=root(a),root(b)
        if a!=b:parent[b]=a;return True
        return False
    def arg(a):
        if 'slot' in a:return env[a['slot']]
        return ('literal',json.dumps(a,sort_keys=True))
    for atom in rule['query']:
        name=atom['call'].get('table')
        if name in tables and tables[name]['kind']=='constructor':facts.append((name,tuple(arg(a) for a in atom['args']),False))
    for i,op in enumerate(rule['effects']):
        kind=op['kind'];name=op.get('call',{}).get('table')
        if kind=='copy':env[op['dst']]=arg(op['arg'])
        elif kind=='union':union(*[arg(a) for a in op['args']])
        elif kind in ('construct','set') and name in tables and tables[name]['kind']=='constructor':
            args=tuple(arg(a) for a in op['args'])
            if kind=='construct':env[op['dst']]=('result',i);result=env[op['dst']]
            else:result=arg(op['value'])
            facts.append((name,args+(result,),True))
        else:return None,dict(operation=i,reason=kind+': ordered, mutable or unsupported effect')
    # Congruence is discharged in Bake, never installed as a runtime repair list.
    changed=True
    while changed:
        changed=False;index={}
        for name,args,_ in facts:
            args=tuple(root(a) for a in args);key=(name,args[:-1])
            if key in index:changed=union(index[key],args[-1]) or changed
            else:index[key]=args[-1]
    facts=[(name,tuple(root(a) for a in args),new) for name,args,new in facts]
    return facts,None


def match_consumer(rule,facts,limit=256):
    index=defaultdict(list)
    for i,(name,args,new) in enumerate(facts):index[name].append((i,args,new))
    atoms=rule['query']
    if not atoms or any(a['call'].get('table') not in index for a in atoms):return [],False
    order=sorted(range(len(atoms)),key=lambda i:len(index[atoms[i]['call']['table']]))
    states=[({},[],False)]
    for at in order:
        atom=atoms[at];next_states=[]
        for env,witnesses,new in states:
            for fact,values,fresh in index[atom['call']['table']]:
                if len(values)!=len(atom['args']):continue
                local=dict(env);ok=True
                for arg,value in zip(atom['args'],values):
                    if 'slot' in arg:
                        slot=arg['slot']
                        if slot in local and local[slot]!=value:ok=False;break
                        local[slot]=value
                    elif ('literal',json.dumps(arg,sort_keys=True))!=value:ok=False;break
                if ok:next_states.append((local,witnesses+[(at,fact)],new or fresh))
                if len(next_states)>limit:return [],True
        states=next_states
    inputs=[i for i,s in enumerate(rule['slots']) if s['definition']=='query']
    # Require an RHS fact occurrence. It may reuse existing information: this
    # is NOT a novelty proof and cannot alone drive saturation.
    out=[];seen=set()
    for env,witnesses,new in states:
        if not new or any(i not in env for i in inputs):continue
        key=tuple((i,env[i]) for i in inputs)
        if key not in seen:seen.add(key);out.append(dict(inputs=key,witnesses=sorted(witnesses),requires_novelty_check=True))
    return out,False


def compile_catalog(recipe):
    tables={t['name']:t for t in recipe['tables']};rules=recipe['rules']
    cells=[];boundaries=[];edges=[];identity_entries_removed=0;inverted=defaultdict(set)
    for rid,r in enumerate(rules):
        for atom in r['query']:
            name=atom['call'].get('table')
            if name:inverted[name].add(rid)
    for rid,r in enumerate(rules):
        facts,mark=complete_template(r,tables)
        if mark:boundaries.append(dict(rule=rid,**mark));cells.append(None);continue
        cells.append(facts)
        candidates=set().union(*(inverted[name] for name,_,new in facts if new)) if any(new for _,_,new in facts) else set()
        for cid in sorted(candidates):
            consumer=rules[cid]
            if any(tables.get(a['call'].get('table'),{}).get('kind')!='constructor' for a in consumer['query']):continue
            entries,exhausted=match_consumer(consumer,facts)
            if exhausted:boundaries.append(dict(rule=rid,consumer=cid,reason='Bake match capacity'));continue
            for entry in entries:
                if rid==cid and all(tuple(ref)==('input',slot) for slot,ref in entry['inputs']):
                    identity_entries_removed+=1;continue
                edges.append(dict(producer=rid,consumer=cid,source_set=r['metadata'].get('source_set'),target_set=consumer['metadata'].get('source_set'),**entry))
    return dict(schema='cell-token-successors/v1',cells=cells,edges=edges,boundaries=boundaries,identity_entries_removed=identity_entries_removed,
        obligations=['Seed Cell assumptions must be established before entry',
        'Source Run ordering and visibility boundaries remain authoritative',
        'Symbols describe terms, never physical result addresses',
        'Unknown external joins and uncovered rules need explicit CPU marks',
        'Generated Cell identity/duplicate handling and token capacity remain runtime obligations'])


def main():
    p=argparse.ArgumentParser();p.add_argument('program',type=Path);p.add_argument('output',type=Path);args=p.parse_args()
    program=json.loads(args.program.read_text());out=compile_catalog(program['recipe']);out['program_sha256']=program['sha256'];args.output.write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(dict(rules=len(out['cells']),closed_effect_templates=sum(c is not None for c in out['cells']),transitions=len(out['edges']),producers=len({e['producer'] for e in out['edges']}),consumers=len({e['consumer'] for e in out['edges']}),cross_ruleset=sum(e['source_set']!=e['target_set'] for e in out['edges']),boundaries=len(out['boundaries']),scope='compile-time coverage, not runtime takeover')))

if __name__=='__main__':main()

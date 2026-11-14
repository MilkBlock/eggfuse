"""Certified semantic-token aliases, separate from physical payload addresses.

Opt-in standalone GPU prototype. Bake proves sealed constructor/Eq containment;
no learned score authorizes containment. Unsupported effects stay on the old path.
The directory contains references, never copied bindings or a runtime fact graph.
"""
import numpy as np


def _sealed(rule):
    # Conservative SSA subset: no overwritten query/result slots, mutable reads,
    # primitives, guards, deletion or visibility effects.
    if rule.get('query_literal_guards'):
        return None
    facts=set(); equal=[]; written={i for i,s in enumerate(rule['slots']) if s['definition']=='query'}
    def slots(args):
        if any(set(a)!={'slot'} for a in args):raise ValueError('non-slot operand')
        return tuple(a['slot'] for a in args)
    try:
        for atom in rule['query']:
            facts.add((atom['call']['table'],slots(atom['args'])))
        for op in rule['effects']:
            kind=op['kind']
            if kind=='union':equal.append(slots(op['args']));continue
            if kind=='set':
                facts.add((op['call']['table'],slots(op['args']+[op['value']])));continue
            if kind not in ('construct','copy'):return None
            dst=op['dst']
            if dst in written:return None
            written.add(dst)
            if kind=='copy':equal.append((dst,slots([op['arg']])[0]))
            else:facts.add((op['call']['table'],slots(op['args'])+(dst,)))
    except (KeyError,ValueError):return None
    return facts,equal


def compile_semantic_transfer(recipe,plan):
    """Prove old sealed facts are present in the destination semantic template."""
    if not plan['covered']:return dict(covered=False,reason='payload_uncovered')
    rules=[recipe['rules'][plan[k]] for k in ('producer','consumer')]
    raw_rules=rules
    rules=[r.get('token_layout',{}).get('rule',r) for r in rules]
    for raw,semantic in zip(raw_rules,rules):
        projection=raw.get('token_layout',{}).get('slot_projection',list(range(len(raw['slots']))))
        if projection[:len(semantic['slots'])]!=list(range(len(semantic['slots']))):
            return dict(covered=False,reason='nonidentity_semantic_prefix')
    tables={t['name']:t['kind'] for t in recipe['tables']}
    proof=[_sealed(r) for r in rules]
    if any(p is None for p in proof):return dict(covered=False,reason='unsupported_semantics')
    if any(tables.get(name)!='constructor' for facts,_ in proof for name,_ in facts):
        return dict(covered=False,reason='mutable_fact')
    ns,nt=map(lambda r:len(r['slots']),rules);mapping=plan['projection'][:ns]
    if np.any(plan['copied'][:ns]):return dict(covered=False,reason='payload_only_fields')
    target_projection=raw_rules[1].get('token_layout',{}).get('slot_projection',list(range(nt)))
    if np.any(mapping<0) or np.any(mapping>=len(target_projection)):
        return dict(covered=False,reason='invalid_projection')
    mapping=np.asarray(target_projection)[mapping]
    if len(mapping)!=ns or np.any(plan['copied'][:ns]) or np.any(mapping>=nt):
        return dict(covered=False,reason='payload_only_fields')
    if any(rules[0]['slots'][i]['sort']!=rules[1]['slots'][int(j)]['sort'] for i,j in enumerate(mapping)):
        return dict(covered=False,reason='sort_mismatch')
    parent=list(range(nt))
    def root(i):
        while parent[i]!=i:i=parent[i]
        return i
    for pair in proof[1][1]:
        if len(pair)!=2:return dict(covered=False,reason='unsupported_eq')
        a,b=pair;parent[root(a)]=root(b)
    target={(name,tuple(root(i) for i in args)) for name,args in proof[1][0]}
    covered=all((name,tuple(root(int(mapping[i])) for i in args)) in target for name,args in proof[0][0])
    covered=covered and all(len(pair)==2 and root(int(mapping[pair[0]]))==root(int(mapping[pair[1]])) for pair in proof[0][1])
    return dict(covered=covered,reason='contained' if covered else 'missing_facts')


def initialize(state,xp):
    return dict(state,token_source=xp.arange(len(state['present']),dtype=xp.int32),
                token_source_generation=state['generation'])


def resolve(state,xp):
    n=len(state['present']);source=state.get('token_source',xp.arange(n,dtype=xp.int32))
    safe=xp.clip(source,0,n-1)
    valid=(source>=0)&(source<n)&state['present'][safe]&state['visible'][safe]&state['settled'][safe]
    valid=valid&(state.get('token_source_generation',state['generation'])==state['generation'][safe])
    valid=valid&~state.get('token_dirty',xp.zeros_like(state['present']))[safe]
    return safe,valid


def adopt(before,after,source,target,transferred,covered,xp):
    if 'token_source' not in before:return after,xp.array(False)
    n=len(before['present']);s=xp.clip(source,0,n-1);t=xp.clip(target,0,n-1)
    refs,valid=resolve(before,xp)
    # The proof describes the source and target templates, not arbitrary owners.
    ok=transferred&covered&(refs[s]==s)&(refs[t]==t)&valid[s]&valid[t]
    aliases=(refs==s)&before['present'];ok=ok&xp.all(~aliases|valid)
    out=dict(after)
    out['token_source']=xp.where(aliases&ok,t,before['token_source'])
    out['token_source_generation']=xp.where(aliases&ok,before['generation'][t],before['token_source_generation'])
    return out,ok

"""Bake proven existing-result effects into one source-slot projection.

No constructor allocation, new Eq, mutable effect or scalar evaluation is hidden
behind settlement. Unsupported rules stay pending without partially applying RHS.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import numpy as np
from collect_observed_corpus import read_bytes


def compile_rule(rule,tables):
    env={i:i for i,s in enumerate(rule['slots']) if s['definition']=='query'}
    facts={};reused=0;copies=0;reflexive=0
    def arg(a):
        if 'slot' in a:return ('slot',env[a['slot']])
        return ('literal',json.dumps(a,sort_keys=True))
    for atom in rule['query']:
        table=atom['call'].get('table')
        if tables.get(table,{}).get('kind')!='constructor':continue
        values=tuple(arg(a) for a in atom['args'])
        if values:facts.setdefault((table,values[:-1]),values[-1])
    for i,op in enumerate(rule['effects']):
        kind=op['kind']
        if kind=='copy':
            value=arg(op['arg']);copies+=1
        elif kind=='construct':
            table=op['call'].get('table');key=(table,tuple(arg(a) for a in op['args']))
            value=facts.get(key)
            if tables.get(table,{}).get('kind')!='constructor' or value is None:
                return dict(covered=False,operation=i,reason='new_constructor_or_unknown_witness')
            reused+=1
        elif kind=='union':
            left,right=map(arg,op['args'])
            if left!=right:return dict(covered=False,operation=i,reason='new_equality')
            reflexive+=1;continue
        else:return dict(covered=False,operation=i,reason='ordered_or_scalar_effect:'+kind)
        if value[0]!='slot':return dict(covered=False,operation=i,reason='literal_slot_value')
        src=value[1];dst=op['dst']
        if rule['slots'][src]['sort']!=rule['slots'][dst]['sort']:
            raise ValueError('alias effect sort mismatch')
        env[dst]=src
    return dict(covered=True,projection=env,reused_constructors=reused,copies=copies,reflexive_unions=reflexive)


def compile_completion(recipe):
    tables={t['name']:t for t in recipe['tables']};rules=recipe['rules']
    width=max((len(r['slots']) for r in rules),default=0)
    proofs=[compile_rule(r,tables) for r in rules]
    projection=np.zeros((len(rules),width),np.int32);valid=np.zeros((len(rules),width),bool)
    for i,p in enumerate(proofs):
        if not p['covered']:continue
        for dst,src in p['projection'].items():projection[i,dst]=src;valid[i,dst]=True
    return dict(projection=projection,valid=valid,covered=np.array([p['covered'] for p in proofs])),proofs


def complete(state,plan,xp):
    """Execute all covered RHS projections in parallel, after matched entry.

    The source slot snapshot and its witnesses must be current and visible.
    Newly projected fields use their actual values, never their storage indices.
    Floating token prediction remains separate from this exact effect proof.
    """
    rule=state['keys'][:,0];in_range=(rule>=0)&(rule<plan['covered'].shape[0])
    rid=xp.clip(rule,0,plan['covered'].shape[0]-1)
    pending=state['present'] & state['active'] & ~state['settled']
    allowed=pending & state['visible'] & in_range & plan['covered'][rid]
    projection=plan['projection'][rid];valid=plan['valid'][rid]
    available=xp.take_along_axis(state['slot_valid'],projection,axis=1)
    ready=xp.all(available | ~valid,axis=1)
    apply=allowed & ready
    values=xp.take_along_axis(state['slots'],projection,axis=1)
    output=dict(state)
    output['slots']=xp.where(apply[:,None]&valid,values,state['slots'])
    output['slot_valid']=state['slot_valid'] | (apply[:,None]&valid)
    output['settled']=state['settled'] | apply
    return output,dict(completed=apply,unsupported=pending & ~plan['covered'][rid],
        unavailable=allowed & ~ready,invisible=pending & ~state['visible'],invalid_rule=pending & ~in_range,
        needs_attention=xp.any(pending & ~apply))


def main():
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    raw=read_bytes(a.source);recipe=json.loads(raw)['recipe'];plan,proofs=compile_completion(recipe)
    result=dict(source_sha256=hashlib.sha256(raw).hexdigest(),rules=len(proofs),
        fully_covered=sum(p['covered'] for p in proofs),
        covered_nonempty_effects=sum(p['covered'] and bool(r['effects']) for p,r in zip(proofs,recipe['rules'])),
        boundaries=dict(Counter(p['reason'] for p in proofs if not p['covered'])),
        static_projection_bytes=plan['projection'].nbytes+plan['valid'].nbytes+plan['covered'].nbytes,
        scope='Recipe-only existing-result effect coverage, not actual GPU Eggcc execution',
        allocations_supported=False,new_equality_supported=False)
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()

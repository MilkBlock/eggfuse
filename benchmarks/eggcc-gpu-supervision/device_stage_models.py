"""Ruleset-authoritative module membership and batch-level device weight selection.

Source annotations are provenance, not the membership of composed rulesets.
Model selection changes only the next batch's parameters; resident Cell tokens
and the original nested schedule remain unchanged.
"""
import numpy as np


def membership(recipe):
    rules=recipe['rules']
    if 'rulesets' not in recipe:
        import json
        names=sorted({r.get('metadata',{}).get('source_set') for r in rules},key=lambda x:json.dumps(x,sort_keys=True))
        matrix=np.array([[r.get('metadata',{}).get('source_set')==s for s in names] for r in rules],bool)
        return names,matrix,False
    sets=recipe['rulesets'];names=[s['name'] for s in sets]
    if len(set(names))!=len(names):raise ValueError('duplicate ruleset definition')
    matrix=np.zeros((len(rules),len(names)),bool)
    for stage,s in enumerate(sets):
        ids=s['rule_ids']
        if len(set(ids))!=len(ids):raise ValueError('duplicate rule membership')
        for rid in ids:
            if type(rid) is not int or not 0<=rid<len(rules):raise ValueError('invalid ruleset rule id')
            matrix[rid,stage]=True
    return names,matrix,True


def compile_bank(names,models):
    """Same-layout matrices share a bank; absent stages remain explicit boundaries.

    Different tensor layouts require a different compiled batch family, not
    silent padding or an accidental universal model.
    """
    if len(set(names))!=len(names) or not names:raise ValueError('distinct stage names required')
    if set(models)-set(names):raise ValueError('model for unknown stage')
    if not models:raise ValueError('no trained stage model')
    first=next(iter(models.values()))
    if not first:raise ValueError('empty stage parameters')
    for model in models.values():
        if model.keys()!=first.keys():raise ValueError('stage parameter keys differ')
        for key,v in model.items():
            if np.shape(v)!=np.shape(first[key]):raise ValueError('incompatible stage tensor layouts')
            if not np.isfinite(v).all():raise ValueError('nonfinite stage parameters')
    tensors={k:np.stack([np.asarray(models[s][k],np.float32) if s in models else np.zeros_like(first[k],dtype=np.float32) for s in names]) for k in first}
    return dict(parameters=tensors,available=np.array([s in models for s in names],bool))


def select(bank,stage,xp):
    n=bank['available'].shape[0];index=xp.clip(stage,0,n-1)
    ready=(stage>=0)&(stage<n)&bank['available'][index]
    return {k:v[index] for k,v in bank['parameters'].items()},ready


def compile_program(recipe,models):
    """Use one authoritative ordering for schedule, Entry stages and model bank."""
    from device_schedule import compile_schedule
    names,_,authoritative=membership(recipe)
    if not authoritative:raise ValueError('scheduled stage models need compiler rulesets')
    schedule,meta=compile_schedule(recipe['control'],names)
    return schedule,compile_bank(names,models),meta

"""Compile exact i64 query constants into bound slots with static ID guards.

No extra fact relation. The input scalar identity registry resolves constants;
values are never compared after rounding to floating point.
"""
from copy import deepcopy
from typed_literal import value
from device_snapshot_import import identity


def lower(recipe):
    out=deepcopy(recipe)
    for rule in out['rules']:
        guards={}
        for atom in rule['query']:
            for field,arg in enumerate(atom['args']):
                if 'slot' in arg:continue
                v=value(arg);slot=len(rule['slots'])
                rule['slots'].append(dict(sort=deepcopy(arg['sort']),definition='query',name='literal_'+str(slot)))
                atom['args'][field]=dict(slot=slot);guards[str(slot)]=identity(v)
        if guards:rule['query_literal_guards']=guards
    return out

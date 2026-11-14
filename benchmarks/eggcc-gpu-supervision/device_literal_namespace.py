"""Reserve compiler constants before GPU result identity allocation.

Only source literals are imported; no future constructors, successful matches or
Eq results are computed. Exact scalar identities stay integer side metadata.
"""
import json
from typed_literal import value
from device_snapshot_import import identity


def bind_effect_literals(recipe,identities):
    ids=dict(identities)
    if sorted(ids.values())!=list(range(len(ids))):raise ValueError('identity registry must be dense and unique')
    for rule in recipe['rules']:
        for op in rule['effects']:
            operands=list(op.get('args',[]))
            operands += [op[k] for k in ('arg','value') if k in op]
            for arg in operands:
                if 'literal' in arg:
                    key=identity(value(arg));ids.setdefault(key,len(ids))
    literal_ids={k:v for k,v in ids.items() if 'eq' not in json.loads(k)}
    return dict(recipe,literal_ids=literal_ids),ids

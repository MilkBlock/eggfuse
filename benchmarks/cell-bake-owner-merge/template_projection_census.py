#!/usr/bin/env python3
"""Join existing instance lifecycles to shared Bake layouts, offline only."""
import json
import sys
from pathlib import Path

def census(path):
    d=json.loads(path.read_text())
    o=d['ownership_storage']
    directory={}
    for component in o['components']:
        shape=o['shapes'][component['shape']]
        for ordinal,cell in enumerate(component['frames']):
            if cell in directory: raise ValueError('duplicate source frame')
            directory[cell]=(shape,ordinal)
    owned=scalar_free=scalar_fields=0
    for frame in d['source_storage']['fact_lifecycle']['frames']:
        for fact in frame['facts']:
            if not fact['owned'] or fact['decoded']: continue
            owned+=1
            shape,ordinal=directory[frame['cell']]
            fields=o['programs'][shape['programs'][ordinal]]['fields'][fact['op']]
            if not fields: raise ValueError('owned fact has no layout')
            scalars=sum(field is None for field in fields)
            scalar_fields+=scalars
            scalar_free+=scalars==0
    if owned!=d['port_index']['live_stable_nodes']:
        raise ValueError('lifecycle census does not cover stable nodes')
    return dict(case=path.stem,program=d['program_sha256'],stable_nodes=owned,
                scalar_free_nodes=scalar_free,scalar_bearing_nodes=owned-scalar_free,
                scalar_fields=scalar_fields,scalar_free_fraction=scalar_free/owned)

if __name__=='__main__':
    root=Path(sys.argv[1])
    rows=[census(root/(c+'.json')) for c in ('fact','loopfact','sum-bits','dot-product')]
    Path(sys.argv[2]).write_text(json.dumps(dict(
        scope='Offline projection eligibility census; no deleted records or measured savings',cases=rows),indent=2)+'\n')
    for row in rows: print(row)

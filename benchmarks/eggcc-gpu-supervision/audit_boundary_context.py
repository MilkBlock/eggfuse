"""Input-only one-hop boundary signatures and captured GPU feature ambiguity."""
import argparse,hashlib,json
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np
from audit_input_relations import restore
from audit_feature_identifiability import ceiling
from device_semantic_template import semantic
from device_boundary_context import compile_context,masks


def signature(c,lane,recipe,scalars):
    boundary=c['boundary'];b=c['bindings'];rid=int(c['rule'])
    p=compile_context(recipe,rid,boundary['slots'].shape[1]);conn,_,_,_=masks(boundary,b,p,np)
    selected=np.flatnonzero(np.any(conn[lane],axis=(0,2)))
    rule=semantic(recipe['rules'][rid])[0];anchors={}
    def scalar(identity,sort):
        v=scalars.get(str(int(identity)))
        if v is None or v['sort']!=sort['name']:raise ValueError('unknown scalar')
        return ('scalar',v)
    values=[]
    for i,s in enumerate(rule['slots']):
        if s['definition']!='query':continue
        sort=s['sort']
        if sort['kind']=='eq':
            key=(sort['name'],int(b['slot_roots'][lane,i]));values.append(('boundary',sort['name'],anchors.setdefault(key,len(anchors))))
        else:values.append(scalar(b['slots'][lane,i],sort))
    neighbors=[]
    for row in selected:
        r=semantic(recipe['rules'][int(boundary['rule'][row])])[0];local={};slots=[]
        for i,s in enumerate(r['slots']):
            if not boundary['slot_valid'][row,i]:raise ValueError('incomplete sealed neighbor')
            sort=s['sort']
            if sort['kind']=='eq':
                key=(sort['name'],int(boundary['slot_roots'][row,i]))
                slots.append(('boundary',sort['name'],anchors[key]) if key in anchors else ('local',sort['name'],local.setdefault(key,len(local))))
            else:slots.append(scalar(boundary['slots'][row,i],sort))
        neighbors.append(json.dumps(({k:r[k] for k in ('slots','query','effects')},slots),sort_keys=True))
    # Local non-boundary IDs are renamed within each neighbor; cross-neighbor
    # sharing away from the boundary is deliberately not claimed canonicalized.
    return json.dumps((values,sorted(neighbors)),sort_keys=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('captures',type=Path,nargs='+');a=p.parse_args()
    names=('resident','plus_boundary_float','one_hop_structure')
    combined={k:defaultdict(Counter) for k in names};parts=[]
    for path in a.captures:
        meta=json.loads(path.with_suffix('.json').read_text())
        if not meta['capture']['passed'] or hashlib.sha256(path.read_bytes()).hexdigest()!=meta['capture']['artifact_sha256']:raise ValueError('unverified capture')
        groups={k:defaultdict(Counter) for k in names};signatures=[]
        with np.load(path) as f:
            prefixes=[k[:-4] for k in f.files if k.startswith('capture/') and k.endswith('/rule') and '/witness/' not in k and '/boundary/' not in k]
            prefixes.sort(key=lambda s:tuple(map(int,s.strip('/').split('/')[1:])))
            for prefix in prefixes:
                c=restore(f,prefix)
                if not bool(c['recorded']):continue
                for lane in np.flatnonzero(c['accepted']):signatures.append(signature(c,lane,meta['recipe'],meta['seed_scalars']))
            if len(signatures)!=len(f['features']):raise ValueError('sample alignment')
            base_features=f['features']
            if any('/request/boundary_features' in k for k in f.files):
                width=f['boundary_features'].shape[1]
                if base_features.shape[1]<=width or not np.array_equal(base_features[:,-width:],f['boundary_features']):raise ValueError('live feature schema mismatch')
                base_features=base_features[:,:-width]
            for i,rid in enumerate(f['rules']):
                rule=meta['semantic_recipe']['rules'][meta['source_rules'].index(int(rid))]
                static=json.dumps({k:rule[k] for k in ('slots','query','effects')},sort_keys=True)
                target=tuple(f['target_eq_classes'][i,:len(rule['slots'])].tolist())
                x=base_features[i].tobytes()
                keys=dict(resident=(static,x),plus_boundary_float=(static,x,f['boundary_features'][i].tobytes()),one_hop_structure=(static,signatures[i]))
                for k,v in keys.items():groups[k][v][target]+=1;combined[k][v][target]+=1
        parts.append(dict(case=meta['capture']['case'],partition=meta['capture']['partition'],sha256=meta['capture']['artifact_sha256'],ceilings={k:ceiling(v) for k,v in groups.items()}))
    report=dict(scope='empirical boundary-context ambiguity; not fitted accuracy',parts=parts,combined={k:ceiling(v) for k,v in combined.items()},
        grouping_uses_labels=False,limitations=['One-hop signature omits sharing between non-boundary neighbor ports','Floating equality is bitwise, not a robustness or generalization guarantee','Final completion targets are never features'])
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()

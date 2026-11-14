"""Empirical deterministic ceilings for identical observable Cell inputs.

Labels only score groups; they never determine the input grouping.
"""
import argparse,hashlib,json
from collections import defaultdict,Counter
from pathlib import Path
import numpy as np
from audit_input_relations import restore
from device_match_capture import audit
from device_semantic_template import semantic


def context(c,lane,recipe,scalars):
    eqs={};sources={}
    def value(sort,identity):
        if sort['kind']=='eq':
            key=(sort['name'],int(identity))
            return ('eq',sort['name'],eqs.setdefault(key,len(eqs)))
        v=scalars.get(str(int(identity)))
        if v is None or v['sort']!=sort['name']:raise ValueError('unknown scalar identity')
        return ('scalar',v)
    rid=int(c['rule']);rule=semantic(recipe['rules'][rid])[0];b=c['bindings'];w=c['witness']
    inputs=[]
    for i,s in enumerate(rule['slots']):
        if s['definition']=='query':inputs.append(value(s['sort'],b['slot_roots' if s['sort']['kind']=='eq' else 'slots'][lane,i]))
    neighbors=[]
    for ai in range(w['rule'].shape[1]):
        sr=int(w['rule'][lane,ai]);source=semantic(recipe['rules'][sr])[0];row=int(b['witness_rows'][lane,ai])
        static={k:source[k] for k in ('slots','query','effects')};values=[]
        for i,s in enumerate(source['slots']):
            if not w['slot_valid'][lane,ai,i]:raise ValueError('incomplete source payload')
            values.append(value(s['sort'],w['slot_roots' if s['sort']['kind']=='eq' else 'slots'][lane,ai,i]))
        neighbors.append((sources.setdefault(row,len(sources)),static,int(b['witness_records'][lane,ai]),values))
    return json.dumps((inputs,neighbors),sort_keys=True,separators=(',',':'))


def ceiling(groups):
    n=sum(sum(v.values()) for v in groups.values());best=sum(max(v.values()) for v in groups.values())
    return dict(samples=n,distinct_inputs=len(groups),conflicting_input_groups=sum(len(v)>1 for v in groups.values()),
        samples_in_conflicting_groups=sum(sum(v.values()) for v in groups.values() if len(v)>1),maximum_exact_samples=best,maximum_fraction=best/n if n else None)


def main():
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('captures',type=Path,nargs='+');a=p.parse_args()
    combined={k:defaultdict(Counter) for k in ('floating_input','plus_input_relations','full_selected_sources')};parts=[]
    for path in a.captures:
        meta=json.loads(path.with_suffix('.json').read_text());sha=hashlib.sha256(path.read_bytes()).hexdigest()
        if sha!=meta['capture']['artifact_sha256'] or not meta['capture']['passed'] or 'semantic_recipe' not in meta:raise ValueError('unverified semantic capture')
        groups={k:defaultdict(Counter) for k in combined};contexts=[]
        with np.load(path) as f:
            prefixes=[k[:-4] for k in f.files if k.startswith('capture/') and k.endswith('/rule') and '/witness/' not in k]
            prefixes.sort(key=lambda s:tuple(map(int,s.strip('/').split('/')[1:])))
            for prefix in prefixes:
                c=restore(f,prefix)
                if not bool(c['recorded']):continue
                if not audit(meta['recipe'],c)['passed']:raise ValueError('invalid source')
                for lane in np.flatnonzero(c['accepted']):contexts.append(context(c,lane,meta['recipe'],meta['seed_scalars']))
            if len(contexts)!=len(f['features']):raise ValueError('sample alignment')
            for i,rid in enumerate(f['rules']):
                rule=meta['semantic_recipe']['rules'][meta['source_rules'].index(int(rid))]
                static=json.dumps({k:rule[k] for k in ('slots','query','effects')},sort_keys=True)
                y=tuple(f['target_eq_classes'][i,:len(rule['slots'])].tolist())
                keys=dict(floating_input=(static,f['features'][i].tobytes()),plus_input_relations=(static,f['features'][i].tobytes(),f['input_relations'][i].tobytes()),full_selected_sources=(static,contexts[i]))
                for k,key in keys.items():groups[k][key][y]+=1;combined[k][key][y]+=1
        parts.append(dict(case=meta['capture']['case'],partition=meta['capture']['partition'],sha256=sha,ceilings={k:ceiling(g) for k,g in groups.items()}))
    report=dict(scope='empirical exact-input ambiguity audit; not accuracy of a fitted model',parts=parts,combined={k:ceiling(g) for k,g in combined.items()},
        backpropagation=False,grouping_uses_labels=False,limitations=['Ceilings apply only to this empirical sample set and stated inputs','Full selected-source signature is an offline diagnostic, not a GPU feature implementation','No extra graph neighbors or future outputs enter context signatures'])
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()

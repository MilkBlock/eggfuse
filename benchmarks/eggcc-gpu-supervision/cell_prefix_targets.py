"""Supervise next Cell Entry selection, before constructing complete tuples.

Labels come from exhaustive bounded synthetic candidate audits. No inference
algorithm is implemented here. Identity references are labels, never floats.
"""
import argparse,hashlib,json
from pathlib import Path
import numpy as np


def build(data):
    states={};complete_labels={}
    for i in range(len(data['valid'])):
        entries=tuple((int(s),int(r)) for s,r in zip(data['entry_sources'][i],data['entry_records'][i]) if r>=0)
        case=int(data['case'][i]);rule=int(data['rule'][i])
        identity=(case,rule,entries);label=bool(data['valid'][i]>0)
        if identity in complete_labels and complete_labels[identity]!=label:
            raise ValueError('Entry tuple has conflicting validity labels')
        complete_labels[identity]=label
        for depth in range(len(entries)):
            key=(case,rule,entries[:depth])
            row=states.setdefault(key,dict(offered=set(),legal=set()))
            row['offered'].add(entries[depth])
            if data['valid'][i]>0:row['legal'].add(entries[depth])
    for (case,rule,entries),expected in complete_labels.items():
        accepted=all(entries[d] in states[(case,rule,entries[:d])]['legal'] for d in range(len(entries)))
        if accepted!=expected:raise ValueError('prefix labels do not preserve candidate acceptance')
    result=[]
    for (case,rule,prefix),row in sorted(states.items()):
        result.append(dict(case=case,rule=rule,prefix=prefix,
                           offered=sorted(row['offered']),legal_next=sorted(row['legal'])))
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('dataset',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    manifest=json.loads(a.dataset.with_suffix('.json').read_text())
    digest=hashlib.sha256(a.dataset.read_bytes()).hexdigest()
    if not manifest.get('current_state_inputs') or manifest['dataset_sha256']!=digest:raise ValueError('verified current-state data required')
    bank=manifest['context_bank'];path=a.dataset.parent/bank['file']
    if hashlib.sha256(path.read_bytes()).hexdigest()!=bank['sha256']:raise ValueError('context bank mismatch')
    rows=build(dict(np.load(a.dataset,allow_pickle=False)))
    out=dict(scope='bounded synthetic prefix-selection labels; no runtime candidate reduction yet',
             dataset_sha256=digest,context_bank=bank,states=len(rows),
             multiple_choices=sum(len(r['legal_next'])>1 for r in rows),
             dead_prefixes=sum(not r['legal_next'] for r in rows),rows=rows)
    a.output.write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps({k:v for k,v in out.items() if k!='rows'}))


if __name__=='__main__':main()

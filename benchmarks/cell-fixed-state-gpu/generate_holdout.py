"""Freeze additional completion-preserving entrances before model evaluation.
Derived-fact additions deliberately target the known catalog; not natural traffic.
"""
import argparse
import hashlib
import json
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--corpus',type=Path,required=True);p.add_argument('--inputs',type=Path,required=True)
p.add_argument('--output',type=Path,required=True);p.add_argument('--limit',type=int,default=120)
p.add_argument('--split',choices=['train','validation','test'],default='test')
a=p.parse_args();corpus=json.loads(a.corpus.read_text());original=json.loads(a.inputs.read_text());sources={r['id']:r for r in original['cases']}
by_label={}
for r in corpus['records']:
    if r['split']==a.split:by_label.setdefault(r['completion_key'],[]).append(r)
candidates=[];seen=set()
for label,records in sorted(by_label.items()):
    for r in sorted(records,key=lambda r:r['id']):
        reps=[];terms=[]
        for facts in r['completion']:
            current=[]
            for op,args in facts:
                rendered=[reps[v] if k=='eq' else str(v) for k,_,v in args]
                current.append('('+op+' '+' '.join(rendered)+')')
            reps.append(current[0]);terms.extend(current)
        original_case=sources[r['id']]
        prefix=original_case['source'].split('(run-schedule')[0]
        for term in sorted(set(terms)):
            source=prefix+term+'\n(run-schedule (saturate (run always-run)))\n'
            key=hashlib.sha256(source.encode()).hexdigest()
            if key in seen:continue
            seen.add(key);candidates.append(dict(id='fresh-'+key[:16],source=source,verify_ruleset='always-run',native_reference=True,
                metadata=dict(parent=r['id'],parent_split=a.split,added_derived_fact=term,expected_known_completion=label)))
# Deterministic round-robin over labels, independent of model predictions.
groups={label:[] for label in sorted(by_label)}
for row in candidates:groups[row['metadata']['expected_known_completion']].append(row)
selected=[]
for index in range(max(map(len,groups.values()))):
    for label,rows in groups.items():
        if index<len(rows):selected.append(rows[index])
selected=selected[:a.limit]
a.output.parent.mkdir(parents=True,exist_ok=True)
a.output.write_text(json.dumps(dict(cases=selected,scope='new derived-fact entrances into known completions; frozen selection before evaluation',
    generation_uses_completion_graphs=True,model_used_for_selection=False,parent_split=a.split,source_corpus_sha256=hashlib.sha256(a.corpus.read_bytes()).hexdigest()),indent=2)+'\n')
print('generated',len(selected))

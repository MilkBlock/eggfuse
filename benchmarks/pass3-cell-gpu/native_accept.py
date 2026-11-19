"""Reviewed dot-product final-state contract, independent of the Run trace checks."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'marker-handoff'))
from choice_diagnosis import SOURCE_CORE_SHA256,check_pair,key

DOT_CORE='dece3f6d2a050026ae5fe09479a2793dbd0a94b21cccd92c133093bb8657739b'


def read(path):return json.loads(path.read_text())


def check(root,out):
    if not __debug__:raise ValueError('requires enabled assertions')
    d=root/'native-gpu-dot';baseline=read(root/'sum-bits/program.json');program=read(root/'dot-product/program.json')
    for artifact,wanted in [(baseline,SOURCE_CORE_SHA256),(program,DOT_CORE)]:
        if hashlib.sha256(key(artifact['source_core']).encode()).hexdigest()!=wanted:
            raise ValueError('not a reviewed source core')
    a,b=baseline['recipe'],program['recipe']
    for field in ('tables','rulesets','control'):assert a[field]==b[field],field
    init,=next(s['rule_ids'] for s in b['rulesets'] if s['name']=='initialization')
    assert baseline['initial']==program['initial'] and len(a['rules'])==len(b['rules'])
    for i,(x,y) in enumerate(zip(a['rules'],b['rules'])):
        assert x['query']==y['query']
        if i!=init:
            assert x['effects']==y['effects'] and x['metadata']==y['metadata']
            assert [[s['definition'],s['sort']] for s in x['slots']]==[[s['definition'],s['sort']] for s in y['slots']]
    assert not b['rules'][init]['query'] and {e['kind'] for e in b['rules'][init]['effects']}<= {'copy','construct','set'}
    files={'unmarked':d/'native-source.json','marked':d/'native-legacy.json','gpu':root/'export-dot-product/state.json'}
    states={k:read(p) for k,p in files.items()}
    reports={f'{l}_vs_{r}':check_pair(states[l],states[r],program['source_core']['tables'])
             for l,r in [('unmarked','marked'),('marked','gpu')]}
    report=dict(status='pass' if all(v['status']=='pass' for v in reports.values()) else 'not_verified',
                baseline_core=SOURCE_CORE_SHA256,core=DOT_CORE,init_rule=init,
                unchanged_noninitial_rule_bodies=len(a['rules'])-1,comparisons=reports,
                input_sha256={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in files.items()})
    out.write_text(json.dumps(report,indent=1)+'\n');print(report['status'])
    if report['status']!='pass':raise SystemExit(1)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('out',type=Path)
    a=p.parse_args();check(a.root,a.out)

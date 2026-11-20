"""Derive the executable port schema and width strata for the shared complete-key cohort."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import numpy as np


def read(path):
    return json.loads(path.read_bytes())


def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def compile_schemas(program):
    rules = program['recipe']['rules']
    tables = {t['name']:t['schema'] for t in program['recipe']['tables']}
    admitted = {}
    for cert in program['multi_stage']['stage_entries']:
        rid, pivot = cert['rule'], cert['anchor']
        q = rules[rid]['query']
        if rid in admitted or len(q)!=2 or cert['atoms']!=[1-pivot]:
            continue
        if any('table' not in atom['call'] for atom in q):
            continue
        target_key=q[1-pivot]['args'][:-1]
        if not any('slot' in op for op in target_key):
            continue
        source_slots={op['slot'] for op in q[pivot]['args'] if 'slot' in op}
        if not all('slot' not in op or op['slot'] in source_slots for op in target_key):
            raise ValueError('stage-entry certificate has an unbound key')
        slots={};members=[]
        for i in (pivot,1-pivot):
            name=q[i]['call']['table']
            schema=tables[name];args=q[i]['args']
            if len(args)!=len(schema):
                raise ValueError('table width mismatch')
            fields=[]
            for sort,op in zip(schema,args):
                if 'slot' in op:
                    slot=op['slot']
                    if rules[rid]['slots'][slot]['sort']!=sort:
                        raise ValueError('slot sort differs')
                    fields.append(['param',slots.setdefault(slot,len(slots)),sort['name']])
                else:
                    fields.append(['literal',op['literal'],sort['name']])
            members.append([name,fields])
        signature=canonical(members)
        admitted[rid]=dict(template=hashlib.sha256(signature.encode()).hexdigest(),
                           pivot=pivot,members=members,logical_fields=sum(len(x[1]) for x in members),
                           instance_slots=len(slots),boundary_refs=1)
    return admitted


def measure(root,ref):
    cases=read(root/'collection.json')
    reports={};training=set()
    ordered=sorted(cases,key=lambda n:cases[n]['split']!='train')
    for n in ordered:
        case=cases[n]
        src=(ref if case['split']=='anchor' else root)/n/'program.json'
        artifact=read(src)
        assert artifact['sha256']==case['program']
        plans=compile_schemas(artifact)
        device=(ref/f'release-{n}' if case['split']=='anchor' else root/n/'device')
        with np.load(device/'output.npz') as f:
            counts=Counter(int(r) for r in f['rhs'][:,1] if int(r) in plans)
            assert len(f['runs'])==case['runs']
        by_width=Counter();per_template=Counter()
        for rid,count in counts.items():
            p=plans[rid]
            by_width[p['logical_fields'],p['instance_slots'],p['boundary_refs']]+=count
            per_template[p['template']]+=count
        if case['split']=='train':training.update(per_template)
        reports[n]=dict(split=case['split'],program=case['program'],rules=len(plans),
            active_rules=len(counts),active_templates=len(per_template),bindings=sum(counts.values()),
            width_counts=[[f,s,b,c] for (f,s,b),c in sorted(by_width.items())],
            cold_bindings=sum(c for t,c in per_template.items() if t not in training),
            active_cold_templates=sum(t not in training for t in per_template),
            width5_overflow=sum(c for (f,_,_),c in by_width.items() if f>5),
            width8_overflow=sum(c for (f,_,_),c in by_width.items() if f>8))
    return {'schema':'cell-port-width-census/1','training_template_count':len(training),'cases':reports}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('corpus','reference','output'):parser.add_argument(name,type=Path)
    args=parser.parse_args()
    args.output.write_text(json.dumps(measure(args.corpus,args.reference),indent=1)+'\n')

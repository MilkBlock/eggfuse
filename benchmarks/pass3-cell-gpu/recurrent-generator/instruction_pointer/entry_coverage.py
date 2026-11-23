"""Cover positive EggCC template entries using only native training tapes and pre-write watermarks."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random

from train_anchor_set import training_selection


def read(p):return json.loads(p.read_bytes())


def entries(folder):
    prog=read(folder/'program.json')['recipe']
    rules=prog['rules']
    def template(r):
        body=[r['query'],r['effects'],[(s['sort'],s['definition']) for s in r['slots']],r['metadata']['seminaive']]
        raw=json.dumps(body,sort_keys=True,separators=(',',':')).encode()
        return hashlib.sha256(raw).hexdigest()
    types=[template(r) for r in rules]
    tape=defaultdict(list)
    for p in read(folder/'tape.json')['requests']:tape[p['run']].append(p)
    runs=defaultdict(list)
    with (folder/'memory.jsonl').open() as f:
        for line in f:
            frame=json.loads(line)
            wm=dict(frame['rules'])
            for p in tape[frame['run']]:
                rid=p['rule']
                parents=p['parents']
                anchor=next((i for i,a in enumerate(parents) if not rules[rid]['metadata']['seminaive'] or
                             a['version']>=wm[rid]),None)
                if parents and anchor is None: raise ValueError('no fresh entry')
                origins=tuple('generated' if a['address']['token']>0 else
                              'initial' if a['address']['token']%2 else 'repair' for a in parents)
                runs[frame['run']].append(((types[rid],anchor,origins),p['token']))
    return runs


def split_runs(root,seed):
    selected=list(training_selection(root,seed))
    # Mirror the exact historical train/calibration split. Calibration Runs
    # cannot seed coverage, supply a new example, or rank candidate Runs.
    index=[]
    zero=set()
    for r,runs in selected:
        name=r['directory']
        index.extend((name,k) for k in sorted(runs))
        for p in read(root/name/'tape.json')['requests']:
            if p['run'] in runs and not p['parents']:zero.add((name,p['run']))
    random.Random(seed).shuffle(index)
    nz=max(1,len(zero)//2)
    n=max(1,len(index)//6)
    held=set([x for x in index if x in zero][:nz]+[x for x in index if x not in zero][:n])
    fitted=set(index)-held
    return selected,fitted,held


def plan(root,seed):
    selected,fitted,held=split_runs(root,seed)
    available={}
    observed=set()
    train_templates=set()
    for r,_ in selected:
        if r['origin']!='eggcc': continue
        name=r['directory']
        for run,values in entries(root/name).items():
            key=(name,run)
            if key in held: continue
            labels={x for x,_ in values}
            available[key]=labels
            if key in fitted:observed.update(labels)
            train_templates.update(x[0] for x in labels)
    all_entries=set.union(*available.values())
    missing=all_entries-observed
    add=defaultdict(list)
    while missing:
        best=max(available,key=lambda k:len(available[k]&missing))
        take=available[best]&missing
        if best in fitted or not take:raise ValueError('uncovered entry has no train-only source')
        add[best[0]].append(best[1])
        missing-=take
    augmented=observed.union(*(available[n,k] for n,runs in add.items() for k in runs))
    if augmented!=all_entries:raise ValueError('incomplete coverage plan')
    covered_templates={x[0] for x in observed}
    held_cases={}
    for name in ('fact','loopfact','sum-divisors'):
        # Evaluate the already frozen plan. No held source can alter its choices.
        samples=Counter(entry for values in entries(root/name).values() for entry,_ in values)
        held_cases[name]=dict(required=sum(samples.values()),
            seen_template_before=sum(n for x,n in samples.items() if x[0] in covered_templates),
            seen_template_after=sum(n for x,n in samples.items() if x[0] in train_templates),
            seen_entry_before=sum(n for x,n in samples.items() if x in observed),
            seen_entry_after=sum(n for x,n in samples.items() if x in augmented))
    return dict(seed=seed,training_runs=len(fitted),calibration_runs=len(held),templates_before=len(covered_templates),
                templates_after=len(train_templates),entries_before=len(observed),entries_after=len(augmented),
                additional={n:sorted(v) for n,v in add.items()},held_opportunity=held_cases)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root',type=Path);p.add_argument('out',type=Path)
    p.add_argument('--seed',type=int,default=1703)
    a=p.parse_args();a.out.write_text(json.dumps(plan(a.root,a.seed),indent=2)+'\n')

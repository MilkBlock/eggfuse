"""Replay an entire typed Cell certificate using named reads, on sealed native reference snapshots."""
import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import json
from pathlib import Path

from anchor_set_audit import check
from alternate_proofs import digest
from higher_cell import read
from ripsat_layout import capture


def unpack(rows):
    return [tuple((rid,run,tuple(map(tuple,wires))) for rid,run,wires in steps) for steps in rows]


def verify(folder,donor,layouts,binary,max_steps,*,grow_consumers=False):
    ref,mapped,by_root,_=capture(folder,donor,max_steps,grow_consumers=grow_consumers)
    dest={layout:i for i,layout in enumerate(layouts)}
    samples={}
    observed=set()
    for j,entries in by_root.items():
        for layout,occurrences in entries.items():
            uid=dest.get(layout)
            if uid is None:
                continue
            observed.add(uid)
            if uid in samples:
                continue
            for boundary,ready,first,expected in occurrences:
                if ready and first:
                    samples[uid]=(ref[j]['run'],boundary,expected)
                    break
    schedules=defaultdict(list)
    first_visible={}
    next_run={}
    last=None
    with (folder/'memory.jsonl').open() as frames:
        for line in frames:
            frame=json.loads(line)
            run=frame['run']
            if last is not None:
                next_run[last]=run
            last=run
            for rid,_ in frame['rules']:
                if mapped[rid] is not None:
                    schedules[mapped[rid]].append(run)
            for addr,row in frame['updates']:
                first_visible.setdefault((addr['token'],addr['op']),(run,row['version']))
    sets={rid:set(times) for rid,times in schedules.items()}
    inverse={did:rid for rid,did in enumerate(mapped) if did is not None}
    groups={}
    for uid,(run,_,_) in samples.items():
        groups[uid]=[run]
        needed=defaultdict(set)
        for rid,stage,_ in layouts[uid]:
            needed[stage].add(rid)
        for stage in range(1,len(needed)):
            rules=needed[stage]
            times=schedules[min(rules)]
            at=bisect_right(times,run)
            run=next(t for t in times[at:] if all(t in sets[r] for r in rules))
            groups[uid].append(run)
    tape=read(folder/'tape.json')
    actual=defaultdict(list)
    verdicts=Counter()
    corrupt=Counter()
    for step in range(max(map(len,layouts))):
        probes=[]
        owners={}
        def add(uid,run,rid,parents,control):
            pid=len(probes)+1
            probes.append(dict(token=pid,run=run,rule=inverse[rid],parents=parents))
            owners[pid]=uid,control
        for uid,(_,boundary,expected) in samples.items():
            if step>=len(layouts[uid]) or len(actual[uid])!=step:
                continue
            rid,group,wires=layouts[uid][step]
            run=groups[uid][group]
            parents=[]
            for owner,slot in wires:
                if owner<0:
                    token,pc,version=boundary[slot]
                else:
                    token,applied=actual[uid][owner]
                    pc=slot
                    sealed,version=first_visible[token,pc]
                    if sealed!=next_run[applied]:
                        raise ValueError('return absent at the first sealed boundary')
                parents.append(dict(address=dict(token=token,op=pc),version=version))
            add(uid,run,rid,parents,False)
            if parents and step==len(layouts[uid])-1:
                broken=[dict(parents[0],version=parents[0]['version']+1),*parents[1:]]
                add(uid,run,rid,broken,True)
        if not probes:
            continue
        result=check(folder,binary,tape,probes)
        for run,pid,teacher,reason in result['recall_verdicts']:
            uid,control=owners[pid]
            if control:
                corrupt[reason]+=1
                if teacher is not None:
                    raise ValueError('corrupt final version matched')
            else:
                verdicts[reason]+=1
                if teacher!=samples[uid][2][step]:
                    raise ValueError('replayed Cell resolved to another source binding')
                actual[uid].append((teacher,run))
    complete=[u for u in samples if len(actual[u])==len(layouts[u])]
    if len(complete)!=len(samples):
        raise ValueError('incomplete certificate replay')
    return dict(mode='native teacher replay',observed_catalog_layouts=len(observed),
                complete_layouts=sorted(complete),complete_by_size=dict(Counter(len(layouts[u]) for u in complete)),
                named_steps=dict(verdicts),corrupted_final_control=dict(corrupt))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for k in ('root','donor','catalog','binary','out'):
        parser.add_argument(k,type=Path)
    parser.add_argument('--grow-consumers',action='store_true')
    parser.add_argument('--cases',nargs='+',required=True)
    a=parser.parse_args()
    ls=unpack(read(a.catalog))
    donor=read(a.donor/'program.json')
    result={n:verify(a.root/n,donor,ls,a.binary,max(map(len,ls)),grow_consumers=a.grow_consumers) for n in a.cases}
    a.out.write_text(json.dumps(dict(binary=digest(a.binary),catalog=digest(a.catalog),cases=result),indent=2)+'\n')

"""Measure whether every named side premise of a baked chain existed when its root was issued."""
import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import json
from pathlib import Path

from higher_cell import read, fingerprint


def shapes(donor):
    rules = donor['recipe']['rules']
    leaves = donor['spine_blocks']['entries']
    units = [((None,e['consumer'],e['pivot']),) for e in leaves]
    for join in donor['iterative_bake']['joins']:
        left,right = (units[join[k]] for k in ('left','right'))
        units.append(left+((join['output'],*right[0][1:]),)+right[1:])
    catalog = []
    for uid,unit in enumerate(units[len(leaves):], len(leaves)):
        hops=[]
        for (_,producer,_),(pc,rule,pivot) in zip(unit,unit[1:]):
            effect=rules[producer]['effects'][pc]
            atoms=[(i,a['call']['table']) for i,a in enumerate(rules[rule]['query']) if 'table' in a['call']]
            if (pivot,effect.get('call',{}).get('table')) not in atoms:
                raise ValueError('Bake edge and query pivot have different types')
            pos=next(i for i,(atom,_) in enumerate(atoms) if atom==pivot)
            hops.append(dict(pc=pc,rule=rule,pivot=pos,tables=[t for _,t in atoms]))
        if any(len(h['tables'])>1 for h in hops):
            catalog.append(dict(unit=uid,root=unit[0][1],hops=hops))
    return catalog


def address(ref):
    a=ref['address']
    return a['token'],a['op']


def examples(folder,donor,catalog,observe=None,observe_any=None):
    target=read(folder/'program.json')['recipe']
    rules=donor['recipe']['rules']
    compatible={i for i,r in enumerate(target['rules']) if i<len(rules) and fingerprint(r)==fingerprint(rules[i])}
    scheduled=defaultdict(list)
    timeline=defaultdict(list)
    with (folder/'memory.jsonl').open() as lines:
        for line in lines:
            f=json.loads(line)
            run=f['run']
            for rid,_ in f['rules']: scheduled[rid].append(run)
            for a in f['retired']: timeline[a['token'],a['op']].append((run,None))
            for a,row in f['updates']: timeline[a['token'],a['op']].append((run,row))
    uses=defaultdict(list)
    by_rule=defaultdict(list)
    for req in read(folder/'tape.json')['requests']:
        by_rule[req['rule']].append(req)
        for role,parent in enumerate(req['parents']):
            uses[req['run'],req['rule'],role,*address(parent)].append(req)
    result={}
    for unit in catalog:
        root_rule=unit['root']
        if any(r not in compatible for r in [root_rule]+[h['rule'] for h in unit['hops']]):
            continue
        stats=Counter()
        for root in by_rule[root_rule]:
            stats['roots']+=1
            frontier=[(root,())]
            for hop in unit['hops']:
                nxt=[]
                for parent,external in frontier:
                    times=scheduled[hop['rule']]
                    pos=bisect_right(times,parent['run'])
                    if pos==len(times):continue
                    key=(times[pos],hop['rule'],hop['pivot'],parent['token'],hop['pc'])
                    for child in uses[key]:
                        sides=tuple(p for i,p in enumerate(child['parents']) if i!=hop['pivot'])
                        nxt.append((child,external+sides))
                frontier=nxt
            stats['matched_paths']+=len(frontier)
            positive=False
            for child,sides in frontier:
                problems=set()
                for side in sides:
                    log=timeline[address(side)]
                    ix=bisect_right(log,root['run'],key=lambda pair:pair[0])-1
                    row=log[ix][1] if ix>=0 else None
                    if row is None: problems.add('absent')
                    elif row['version']!=side['version']: problems.add('different_version')
                if observe_any: observe_any(unit,root,child,sides,not problems)
                if problems:
                    stats['+'.join(sorted(problems))]+=1
                else:
                    positive=True
                    stats['available_paths']+=1
                    if observe: observe(unit,root,child,sides)
            stats['roots_with_available_completion']+=positive
        result[unit['unit']]=dict(stats)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('root','donor','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',required=True)
    a=p.parse_args()
    donor=read(a.donor/'program.json')
    catalog=shapes(donor)
    report={n:examples(a.root/n,donor,catalog) for n in a.cases}
    a.out.write_text(json.dumps(dict(catalog=catalog,cases=report),indent=2)+'\n')

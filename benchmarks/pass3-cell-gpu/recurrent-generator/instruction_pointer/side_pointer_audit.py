"""Score the frozen side head on complete typed domains for teacher roots with a visible side label."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

import torch

from anchor_set_audit import check
from higher_cell import read
from history import History
from side_boundary import address, examples
from side_pointer import LiveSide
from typed_content import TypedContentCatalog


@torch.no_grad()
def audit(folder,donor,head,seed,binary):
    policy=LiveSide(head)
    target=read(folder/'program.json')
    compatible=[]
    policy.extend(compatible,target['recipe'])
    labels=defaultdict(set)
    children=defaultdict(list)
    def label(unit,root,child,sides,available):
        children[unit['unit'],root['token']].append(child)
        if available: labels[unit['unit'],root['token']].add(address(sides[0]))
    examples(folder,donor,policy.spec['units'],observe_any=label)
    by_run=defaultdict(list)
    tape=read(folder/'tape.json')
    for req in tape['requests']:
        if req['rule'] in policy.options:by_run[req['run']].append(req)
    history=History(TypedContentCatalog(target),seed,cache_ports=True)
    stats=defaultdict(Counter)
    probes=[]
    origins={}
    with (folder/'memory.jsonl').open() as lines:
        for line in lines:
            frame=json.loads(line)
            snap=history.snapshot(frame)
            for req in by_run[snap.run]:
                i,_,_=policy.options[req['rule']]
                unit=policy.spec['units'][i]['unit']
                positive=labels.get((unit,req['token']),set())
                pred=dict(req)
                policy.choose(pred,history,snap)
                s=stats[unit]
                s['given_teacher_roots']+=1
                s['labelled_roots']+=bool(positive)
                s['roots_with_teacher_path']+=bool(children.get((unit,req['token'])))
                if 'side' in pred:
                    s['issued']+=1
                    s['matched_recorded_side']+=address(pred['side']) in positive
                    if (unit,req['token']) in children:
                        pivot=policy.spec['units'][i]['side'][0]
                        for child in children[unit,req['token']]:
                            refs=child['parents'].copy()
                            refs[1-pivot]=pred['side']
                            probe_id=len(probes)+1
                            probes.append(dict(token=probe_id,rule=child['rule'],run=child['run'],parents=refs))
                            origins[probe_id]=(unit,req['token'],child['token'],bool(positive))
                elif positive:s['abstained_on_label']+=1
    confirmed=set()
    audit=check(folder,binary,tape,probes)
    for run,probe_id,credited,reason in audit['recall_verdicts']:
        unit,root,expected,was_visible=origins[probe_id]
        if credited==expected:
            confirmed.add((unit,root,was_visible))
        stats[unit]['native_'+reason]+=1
    for unit,_,was_visible in confirmed:
        key='same_commit_roots' if was_visible else 'rescued_via_other_address'
        stats[unit][key]+=1
    return dict(stats=stats,head=policy.spec['weights'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('root','donor','head','binary','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',required=True)
    a=p.parse_args();torch.set_num_threads(1)
    seeds={r['directory']:r['seed'] for r in read(a.root/'manifest.json')}
    donor=read(a.donor/'program.json')
    result={n:audit(a.root/n,donor,a.head,1703+seeds.get(n,0),a.binary) for n in a.cases}
    a.out.write_text(json.dumps(result,indent=2)+'\n')

"""Measure the rule choice before reading parents on frozen native source Run snapshots."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random

import torch
from actor import InstructionActor
from history import load
from online import lane_choice


def score(actor,cat,frame,nodes):
    good=set(frame.targets)
    rules={rid for rid,_ in good}
    mem=actor.memory(cat,frame,nodes)
    n=Counter(runs=1,teacher_rules=len(rules),teacher_bindings=len(good))
    chosen=set()
    exact=set()
    for lane in range(actor.lanes.num_embeddings):
        state=actor.actions(cat,mem,lane)
        rid,refs=lane_choice(actor,cat,mem,state)
        n['lanes']+=1
        if rid is None:
            n['stop']+=1
            continue
        n['rule_chosen']+=1
        chosen.add(rid)
        if rid not in rules:
            n['rule_without_winner']+=1
            continue
        n['correct_rule_choices']+=1
        if not cat.atoms[rid]:
            n['correct_rule_zero_table_parents']+=1
        else:
            n['correct_rule_requiring_parent']+=1
            n['exact_required_parents']+=int((rid,refs) in good)
        if refs is None:
            n['correct_rule_without_complete_parents']+=1
        elif (rid,refs) in good:
            n['correct_rule_exact_parents']+=1
            exact.add((rid,refs))
        else:
            n['correct_rule_other_parents']+=1
    n.update(covered_distinct_rules=len(chosen&rules),exact_distinct_requests=len(exact),
             empty_runs=int(not rules),empty_correct_stop=int(not rules and not chosen))
    return n


@torch.no_grad()
def audit(root,weights,output,samples,seed,field):
    if samples<1:
        raise ValueError('empty sample budget')
    torch.set_num_threads(1)
    actor=InstructionActor(field_pointer=field).eval()
    actor.load_state_dict(torch.load(weights,weights_only=True,map_location='cpu'))
    manifest=json.loads((root/'manifest.json').read_bytes())
    report=dict(mode='shadow',wave=1,seed=seed,field_pointer=field,
                weights_sha256=hashlib.sha256(weights.read_bytes()).hexdigest(),cases={})
    for rec in (r for r in manifest if r['origin']=='eggcc'):
        busy=set(rec['busy_runs'])
        strata={'with_commits':sorted(busy),'without_commits':sorted(set(range(1,rec['runs']+1))-busy)}
        rng=random.Random(seed+rec['seed'])
        case={}
        for label,runs in strata.items():
            selected=sorted(rng.sample(runs,min(samples,len(runs))))
            totals=Counter()
            # Keep only a few materialized snapshots resident.
            for i in range(0,len(selected),4):
                cat,frames=load(root/rec['directory'],seed,set(selected[i:i+4]))
                nodes=actor.template_graph(cat)
                for frame in frames:
                    totals+=score(actor,cat,frame,nodes)
            case[label]=dict(population=len(runs),sample=selected,counts=totals)
        report['cases'][rec['workload']]=dict(split=rec['split'],**case)
        output.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('root','weights','output'):
        p.add_argument(key,type=Path)
    p.add_argument('--samples',type=int,default=16)
    p.add_argument('--seed',type=int,default=1967)
    p.add_argument('--field-pointer',action='store_true')
    a=p.parse_args()
    audit(a.root,a.weights,a.output,a.samples,a.seed,a.field_pointer)

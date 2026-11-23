"""Measure the rule choice before reading parents on frozen native source Run snapshots."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random

import torch
from rule_read import load_actor
from history import load, stream
from online import lane_choice


def score(actor,cat,frame,nodes):
    good=set(frame.targets)
    rules={rid for rid,_ in good}
    mem=actor.memory(cat,frame,nodes)
    n=Counter(runs=1,teacher_rules=len(rules),teacher_bindings=len(good))
    oracle=Counter()
    chosen=set()
    exact=set()
    for lane in range(actor.lanes.num_embeddings):
        state=actor.actions(cat,mem,lane)
        for teacher_rule in sorted(rules):
            if cat.atoms[teacher_rule]:
                oracle['required_rule_lane_trials']+=1
                decoded,_=actor.references(cat,mem,state[0],teacher_rule)
                oracle['complete_tuple']+=int(decoded is not None)
                oracle['exact_teacher_tuple']+=int((teacher_rule,decoded) in good)
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
    return n,oracle


@torch.no_grad()
def audit(root,weights,output,samples,seed,field):
    if samples<1:
        raise ValueError('empty sample budget')
    torch.set_num_threads(1)
    actor = load_actor(weights, field)
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
            given_rule=Counter()
            # Keep only a few materialized snapshots resident.
            for i in range(0,len(selected),4):
                cat,frames=load(root/rec['directory'],seed,set(selected[i:i+4]))
                nodes=actor.template_graph(cat)
                for frame in frames:
                    ordinary,oracle=score(actor,cat,frame,nodes)
                    totals+=ordinary
                    given_rule+=oracle
            case[label]=dict(population=len(runs),sample=selected,counts=totals,
                oracle_rule=dict(mode="assist",**given_rule))
        report['cases'][rec['workload']]=dict(split=rec['split'],**case)
        output.write_text(json.dumps(report,indent=2)+'\n')


@torch.no_grad()
def held_rule_census(root, weights, output, seed, field):
    """Score only the free rule/Stop decision on every Run of each native holdout."""
    torch.set_num_threads(1)
    actor = load_actor(weights, field)
    report = dict(mode='shadow', decision='rule before any parent read', wave=1,
                  seed=seed, field_pointer=field,
                  weights_sha256=hashlib.sha256(weights.read_bytes()).hexdigest(), cases={})
    for rec in json.loads((root/'manifest.json').read_bytes()):
        if rec['split'] != 'held_eggcc':
            continue
        strata = {key:Counter() for key in ('with_commits', 'without_commits')}
        forced = Counter()
        nodes = None
        for cat, frame in stream(root / rec['directory'], seed):
            if nodes is None:
                nodes = actor.template_graph(cat)
            mem = actor.memory(cat, frame, nodes)
            expected = {rid for rid, _ in frame.targets}
            counts = strata['with_commits' if expected else 'without_commits']
            counts.update(runs=1, teacher_rule_run_pairs=len(expected))
            chosen = set()
            for lane in range(actor.lanes.num_embeddings):
                _, rules, logits = actor.actions(cat, mem, lane)
                action = int(logits.argmax())
                if expected and action == 0:
                    # Diagnostic only: on a busy reference Run, remove Stop
                    # for this ranking read. Never submit its result.
                    forced['stopped_lanes_on_busy_runs'] += 1
                    forced['best_rule_has_winner'] += int(rules[int(logits[1:].argmax())] in expected)
                counts['lane_decisions'] += 1
                if action == 0:
                    counts['stop'] += 1
                else:
                    rid = rules[action - 1]
                    chosen.add(rid)
                    counts['rule_chosen'] += 1
                    counts['correct_rule_choices'] += int(rid in expected)
            counts.update(all_lanes_stopped=int(not chosen),
                          correct_distinct_rule_run_pairs=len(chosen & expected),
                          runs_with_a_correct_rule=int(bool(chosen & expected)))
        if sum(c['runs'] for c in strata.values()) != rec['runs']:
            raise ValueError('missing native Run')
        report['cases'][rec['workload']] = {**strata, 'forced_issue':dict(mode='assist', **forced)}
    if not report['cases']:
        raise ValueError('no held EggCC programs')
    output.write_text(json.dumps(report, indent=2) + '\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('root','weights','output'):
        p.add_argument(key,type=Path)
    p.add_argument('--samples',type=int,default=16)
    p.add_argument('--seed',type=int,default=1967)
    p.add_argument('--field-pointer',action='store_true')
    p.add_argument('--held-rule-census', action='store_true',
                   help='score the free rule head on every held native Run, omit parent decoding')
    a=p.parse_args()
    if a.held_rule_census:
        held_rule_census(a.root, a.weights, a.output, a.seed, a.field_pointer)
    else:
        audit(a.root,a.weights,a.output,a.samples,a.seed,a.field_pointer)

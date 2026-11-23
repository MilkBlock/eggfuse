"""Measure anchor activations and actual signed ownership on a live held-out assist graph."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import subprocess
import torch
from alternate_proofs import digest
from online import execute
from prefix_policy import Policy
from rule_read import load_actor
from rule_screen import LiveRuleScreen,RuleScreen


def evaluate(folder,binary,weights,screen_weights,seed,limit):
    actor=load_actor(weights,True)
    screen=None
    if screen_weights:
        gate=RuleScreen()
        gate.load_state_dict(torch.load(screen_weights, map_location='cpu',weights_only=True))
        screen=LiveRuleScreen(gate.eval())
    truth=defaultdict(set)
    for req in json.loads((folder/'tape.json').read_bytes())['requests']:
        truth[req['run']].add(req['rule'])
    totals=Counter()
    def observe(run,activated):
        totals.update(active=len(activated), productive=len(truth[run]),productive_active=len(activated & truth[run]))
    result=execute(binary,folder/'program.json',actor,seed,assist=True,prefix_policy=Policy(32),
                   rule_screen=screen,activation_observer=observe,run_limit=limit)
    capture=folder/'capture.json'
    ref=json.loads(capture.read_bytes() if capture.is_file() else subprocess.check_output(
        [binary,'reference',folder/'program.json','-','audit']))
    for key,target in [('source_schedule','schedule'),('rhs_by_run','rhs'),('writes_by_run','writes'),
                       ('resume_audit','resumes'),('event_audit','events')]:
        left=result.pop(key)
        # Full audits compare every record. For limited Runs the event stream is not Run-indexed.
        if limit and target in ('events','resumes'):
            continue
        expected=ref[target] if not limit else ref[target][:result['runs']]
        if left != expected:
            raise ValueError('assist rule gate changed '+target)
    if not limit and result['state_sha']!=ref['state_sha']:
        raise ValueError('different final graph')
    result.pop('partial_proof_counts')
    return dict(activations=totals,execution=result)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('root','binary','actor','out'):p.add_argument(n,type=Path)
    p.add_argument('--screen',type=Path)
    p.add_argument('--case',required=True)
    p.add_argument('--runs',type=int)
    a=p.parse_args()
    torch.set_num_threads(1)
    seeds={r['directory']:r['seed'] for r in json.loads((a.root/'manifest.json').read_bytes())}
    data=evaluate(a.root/a.case,a.binary,a.actor,a.screen,1703+seeds.get(a.case,0),a.runs)
    a.out.write_text(json.dumps(dict(case=a.case,binary=digest(a.binary),weights=digest(a.actor),
                              gate=digest(a.screen) if a.screen else None,**data),indent=2)+'\n')

"""Paired shadow receipt accounting for complete packets and optional partial checks."""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import torch

from alternate_proofs import digest
from online import execute
from prefix_policy import Policy
from rule_read import load_actor


def study(folder, binary, weights, runs, policy, seed, open_anchor=False):
    required = defaultdict(set)
    for p in json.loads((folder/'tape.json').read_bytes())['requests']:
        required[p['run']].add(p['token'])
    actor = load_actor(weights, True)
    if open_anchor:
        if not runs or policy.top_k is None:
            raise ValueError("anchor gate intervention needs named diagnostic Runs and a hard budget")
        actor.thresholds[1] = -torch.inf
    out = execute(binary,folder/'program.json',actor,seed,teacher_tape=folder/'tape.json',
                  prefix_policy=policy,shadow_runs=runs)
    report = out.pop('shadow_report')
    ref = json.loads((folder/'capture.json').read_bytes())
    if any(report[k]!=ref[k] for k in ('schedule','writes','rhs','resumes','events','state_sha')):
        raise ValueError('source Run trajectory changed')
    if report['unused_recall'] or len(report['recall_verdicts']) != out['issued']:
        raise ValueError('unaccounted shadow packet')
    winners, counts = defaultdict(set), defaultdict(Counter)
    for run, token, winner, reason in report['recall_verdicts']:
        counts[run]['issued'] += 1
        if winner is None:
            counts[run][reason] += 1
        elif winner in required[run]:
            counts[run]['verified_matches'] += 1
            winners[run].add(winner)
        else:
            raise ValueError('wrong Run or unknown winner')
    for k in ('rhs_by_run','writes_by_run','source_schedule'):
        del out[k]
    out['by_run'] = {r:dict(required=len(required[r]), recovered=len(winners[r]), winner_ids=sorted(winners[r]),
                            **counts[r]) for r in sorted(runs or range(1,out['runs']+1))}
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ('root','binary','weights','output'):
        parser.add_argument(field,type=Path)
    parser.add_argument('--case',required=True)
    parser.add_argument('--runs',nargs='+',type=int)
    parser.add_argument('--top-k',type=int)
    parser.add_argument('--verify-prefix',action='store_true')
    parser.add_argument('--audit',action='store_true')
    parser.add_argument('--open-anchor-gate',action='store_true',help='diagnose anchor threshold on chosen Runs')
    args=parser.parse_args()
    torch.set_num_threads(1)
    seed={r['directory']:r['seed'] for r in json.loads((args.root/'manifest.json').read_bytes())}.get(args.case,0)
    policy=Policy(args.top_k,args.verify_prefix,args.audit)
    report=study(args.root/args.case,args.binary,args.weights,set(args.runs) if args.runs else None,policy,1703+seed,args.open_anchor_gate)
    args.output.write_text(json.dumps(dict(policy=vars(policy),open_anchor_gate=args.open_anchor_gate,case=args.case,weights_sha256=digest(args.weights),
                                          receiver_sha256=digest(args.binary),result=report),indent=2)+'\n')

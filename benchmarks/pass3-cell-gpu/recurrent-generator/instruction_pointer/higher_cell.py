"""Freeze typed iterative Bake continuations on training tapes, then issue them in native assist."""
import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import hashlib
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import torch
from alternate_proofs import digest
from higher_ownership import HigherOwnership
from online import SourcePanic, execute
from prefix_policy import Policy
from rule_read import load_actor


def read(path):
    return json.loads(path.read_bytes())


def fingerprint(rule):
    return hashlib.sha256(json.dumps(rule, sort_keys=True).encode()).hexdigest()


def compile_catalog(donor, training):
    program = read(donor/'program.json')
    leaves = program['spine_blocks']['entries']
    recipes = [((None,e['consumer']),) for e in leaves]
    for join in program['iterative_bake']['joins']:
        left, right = (recipes[join[s]] for s in ('left','right'))
        recipes.append(left + ((join['output'],right[0][1]),) + right[1:])
    rules = program['recipe']['rules']
    eligible = {}
    for i, recipe in enumerate(recipes[len(leaves):],len(leaves)):
        for (unused,prev),(pc,rid) in zip(recipe,recipe[1:]):
            effect = rules[prev]['effects'][pc]
            table = effect.get('call',{}).get('table')
            inputs = [a['call']['table'] for a in rules[rid]['query'] if 'table' in a['call']]
            if effect['op'] not in ('let','set') or inputs != [table]:
                break
        else:
            eligible[i] = recipe
    scores = Counter()
    roots = Counter()
    for folder in training:
        target = read(folder/'program.json')['recipe']['rules']
        available = {rid for rid in range(min(len(rules), len(target))) if target[rid]==rules[rid]}
        by_rule, uses, scheduled = defaultdict(list), {}, defaultdict(list)
        for packet in read(folder/'tape.json')['requests']:
            by_rule[packet['rule']].append(packet)
            if len(packet['parents']) == 1:
                ref = packet['parents'][0]['address']
                key = (packet['run'], packet['rule'], ref['token'], ref['op'])
                if key in uses:
                    raise ValueError('ambiguous single-parent teacher binding')
                uses[key] = packet
        with (folder/'memory.jsonl').open() as frames:
            for line in frames:
                frame = json.loads(line)
                for rid, _ in frame['rules']:
                    scheduled[rid].append(frame['run'])
        for i,recipe in eligible.items():
            if any(rid not in available for _,rid in recipe):
                continue
            for root in by_rule[recipe[0][1]]:
                roots[i] += 1
                packet = root
                for pc, rid in recipe[1:]:
                    times = scheduled[rid]
                    pos = bisect_right(times,packet['run'])
                    if pos == len(times):
                        break
                    packet = uses.get((times[pos],rid,packet['token'],pc))
                    if not packet:
                        break
                    scores[i] += 1
    best = {}
    for i in eligible:
        root = eligible[i][0][1]
        if scores[i] and (root not in best or scores[i]>scores[best[root]]):
            best[root]=i
    used = {rid for i in best.values() for _,rid in eligible[i]}
    return dict(donor=digest(donor/'program.json'),training={f.name:digest(f/'tape.json') for f in training},
                candidates=len(eligible),fingerprints={str(r):fingerprint(rules[r]) for r in sorted(used)},
                units=[dict(root=r,hops=eligible[i][1:],bake_id=i,training_roots=roots[i],
                            training_steps=scores[i]) for r,i in sorted(best.items())])


def run(folder, binary, weight, policy, seed, arm, ept, audit=True, exclusive=False):
    started = perf_counter()
    units = policy['units']
    rules = read(folder/'program.json')['recipe']['rules']
    compatible = {int(rid) for rid,sig in policy['fingerprints'].items()
                  if int(rid)<len(rules) and fingerprint(rules[int(rid)])==sig}
    units = [u for u in units if {u['root'], *(r for _,r in u['hops'])} <= compatible]
    choices = {u['root']:i for i,u in enumerate(units)}
    omit = {r for u in units for _,r in u['hops']} - choices.keys()
    attach = arm in ('add','replace','owned')
    model = load_actor(weight,True)
    with TemporaryDirectory() as tmp:
        catalog = Path(tmp)/'catalog.json'
        catalog.write_text(json.dumps([dict(root=u['root'],hops=u['hops']) for u in units]))
        def execute_live(limit=None):
            return execute(binary,folder/'program.json',model,seed,assist=not exclusive,prefix_policy=Policy(32),
                           run_limit=limit,audit=audit,audit_ept=ept,higher_catalog=catalog if attach else None,
                           higher_choices=choices if attach else None,
                           higher_ownership=HigherOwnership(units) if arm=='owned' else None,
                           omit_rules=omit if arm in ('replace','withhold') else ())
        failure=None
        try:
            report=execute_live()
        except SourcePanic as error:
            if not exclusive: raise
            failure=dict(run=error.run,charged=error.charged)
            report=execute_live(limit=error.run-1)
            if report['runs']!=error.run-1: raise ValueError('failed to reproduce prefix before panic')
    report['policy_process_wall'] = perf_counter()-started
    ref = read(folder/'capture.json')
    if exclusive:
        common=0
        for i,step in enumerate(report['source_schedule']):
            if (i>=len(ref['schedule']) or step!=ref['schedule'][i] or report['writes_by_run'][i]!=ref['writes'][i]
                    or report['rhs_by_run'][i]!=ref['rhs'][i]):
                break
            common+=1
        return dict(arm=arm,mode='exclusive',weights=digest(weight),binary=digest(binary),program=digest(folder/'program.json'),
                    common_runs=common,reference_runs=ref['runs'],final_equal=failure is None and report['state_sha']==ref['state_sha'],
                    failure=failure,measured_runs=report['runs'],paid=report['issued'],higher=report.get('higher'),
                    independent_search_calls=report['independent_search_calls'])
    for k,source in [('source_schedule','schedule'),('rhs_by_run','rhs'),('writes_by_run','writes'),
                     ('event_audit','events'),('resume_audit','resumes')]:
        value = report.pop(k)
        if (audit or k=='source_schedule') and value!=ref[source]:
            raise ValueError('higher token changed native '+source)
    if report['state_sha'] != ref['state_sha']:
        raise ValueError('different final graph')
    if attach and not report['higher']['counts']['accepted_steps']:
        raise ValueError('higher tokens failed to execute')
    if ept:
        exact = json.loads(subprocess.check_output([binary,'reference',folder/'program.json','-','audit','--ept']))
        ledger = report['ept']
        if (exact['ept']['ledger_sha256']!=ledger['ledger_sha256'] or exact['state_sha']!=report['state_sha']
                or exact['runs']!=ledger['runs'] or exact['matches']!=ref['matches']):
            raise ValueError('effective-operation ledger differs from reference')
        totals = [sum(x) for x in zip(*(ledger[k] for k in ('uncredited','signed_external','signed_internal')),strict=True)]
        if totals!=exact['ept']['uncredited'] or not sum(totals):
            raise ValueError('attributed operations differ from native effective operations')
        signed = sum(ledger['signed_external']) + sum(ledger['signed_internal'])
        ledger['per_external_request'] = signed / report['issued']
        ledger['per_decoded_request'] = signed / (report['issued'] + report.get('withheld_owned_requests',0))
    report.pop('partial_proof_counts')
    return dict(arm=arm,compatible_units=[u['bake_id'] for u in units],program=digest(folder/'program.json'),binary=digest(binary),weights=digest(weight),
                reference_commits=ref['matches'],omitted_standalone_rules=sorted(omit) if arm in ('replace','withhold') else [],
                execution=report)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='mode',required=True)
    fit=sub.add_parser('compile')
    for key in ('root','donor','out'): fit.add_argument(key,type=Path)
    test=sub.add_parser('run')
    for key in ('root','binary','weights','catalog','out'): test.add_argument(key,type=Path)
    test.add_argument('--case',required=True)
    test.add_argument('--exclusive',action='store_true')
    test.add_argument('--ept',action='store_true')
    test.add_argument('--arm',choices=['base','add','withhold','replace','owned'],required=True)
    args=parser.parse_args()
    manifest=read(args.root/'manifest.json')
    if args.mode=='compile':
        training=[args.root/r['directory'] for r in manifest if r['split']=='train' and r['origin']=='eggcc']
        if args.donor.resolve() not in [p.resolve() for p in training]:
            raise ValueError('Bake donor must be a training program')
        result=compile_catalog(args.donor,training)
    else:
        torch.set_num_threads(1)
        seed=1703+next((r['seed'] for r in manifest if r['directory']==args.case),0)
        result=run(args.root/args.case,args.binary,args.weights,read(args.catalog),seed,args.arm,args.ept,exclusive=args.exclusive)
    args.out.write_text(json.dumps(result,indent=2)+'\n')

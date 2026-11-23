"""Recall of distinct native teacher commits on each sealed source Run snapshot."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
from statistics import mean
import subprocess
from tempfile import TemporaryDirectory

import torch

from catalog import Catalog
from history import History
from online import issue_run, execute
from rule_read import load_actor


def read(path):
    return json.loads(path.read_bytes())


@torch.no_grad()
def proposals(folder, model, seed, waves, oracle_rules=None):
    cat = getattr(model,'catalog_type',Catalog)(read(folder/'program.json'))
    history = History(cat,seed)
    nodes = model.template_graph(cat)
    packets = []
    reasons = Counter()
    with (folder/'memory.jsonl').open() as frames:
        for line in frames:
            row = json.loads(line)
            wanted = None if oracle_rules is None else oracle_rules.get(row['run'], ())
            frame = history.snapshot(row)
            if wanted is not None and not wanted:
                continue
            if wanted is None:
                actions, _, ending = issue_run(model,cat,frame,nodes,waves)
                reasons[ending] += 1
            else:
                # Offline upper bound only. The frozen parent head reads one
                # lane state per (Run, rule, lane), regardless of past receipts.
                mem = model.memory(cat,frame,nodes)
                _,lanes,_ = model.setup(cat,frame,mem)
                actions = []
                for rid in sorted(wanted):
                    for lane in lanes:
                        refs,_ = model.references(cat,mem,lane,rid)
                        reasons['oracle_rule_lane_choices'] += 1
                        if refs is not None:
                            actions.append((rid,refs))
            for rid, refs in actions:
                parents = []
                for alias, pc in refs:
                    addr = (history.inverse[alias],pc)
                    parents.append(dict(address=dict(token=addr[0],op=pc),version=history.visible[addr]['version']))
                packets.append(dict(run=frame.run,rule=rid,token=len(packets)+1,parents=parents))
    return packets, reasons


def audit(folder, binary, model, seed, waves, output, control=False, live=False, blind=False, oracle=False):
    teacher = read(folder/'tape.json')
    native = read(folder/'capture.json')
    if live:
        if control:
            raise ValueError('teacher control uses fixed proposal replay')
        requests = []
        execution = execute(binary, folder/'program.json', model, seed, waves, live_receipts=True,
                      teacher_tape=folder/'tape.json', observe_packets=requests.extend, mask_receipts=blind)
        checked = execution.pop('shadow_report')
        endings = execution['wave_endings']
    else:
        rules = None
        if oracle:
            rules = defaultdict(set)
            for packet in teacher['requests']:
                rules[packet['run']].add(packet['rule'])
        requests, endings = proposals(folder,model,seed,waves,rules) if not control else (teacher['requests'],{})
        with TemporaryDirectory() as tmp:
            tape = Path(tmp)/'probe.json'
            tape.write_text(json.dumps({**teacher,'requests':requests}))
            checked = json.loads(subprocess.check_output([binary,'replay',folder/'program.json',folder/'tape.json',
                                                         'audit','--recall',tape]))
    if (checked['unused_recall'] or checked['unused'] or checked['counts']['accepted'] != native['matches']
            or any(checked[k] != native[k] for k in ('rhs','writes','schedule','state_sha','resumes','events'))):
        raise ValueError('teacher trajectory or probe ledger changed')
    expected = defaultdict(dict)
    for r in teacher['requests']:
        expected[r['run']][r['token']] = r
    by_run = defaultdict(list)
    by_token = {r['token']:r for r in requests}
    seen = set()
    for run, token, winner, reason in checked['recall_verdicts']:
        if token in seen or by_token[token]['run'] != run:
            raise ValueError('unexpected or duplicate packet verdict')
        if winner is not None and expected[run][winner]['rule'] != by_token[token]['rule']:
            raise ValueError('cross-rule match')
        seen.add(token)
        by_run[run].append((winner,token,reason))
    if seen != set(by_token):
        raise ValueError('missing packet verdict')
    rows = []
    rejects = Counter()
    aliased = 0
    for run, step in enumerate(native['schedule'],1):
        want = expected[run]
        if len(want)!=step[4]:
            raise ValueError('teacher packet count differs from committed RHS count')
        verdicts = by_run[run]
        hits = {w for w,_,_ in verdicts if w is not None}
        matches = sum(w is not None for w,_,_ in verdicts)
        for w,t,reason in verdicts:
            if w is None:
                rejects[reason] += 1
        aliased += sum(all(by_token[t]['parents'] != want[w]['parents']
                           for v,t,_ in verdicts if v==w) for w in hits)
        rows.append(dict(run=run,ruleset=step[0],teacher_commits=len(want),issued=len(verdicts),
                         recovered=len(hits),duplicate_matches=matches-len(hits),
                         off_reference=sum(r=='off_reference' for _,_,r in verdicts),
                         rejected=sum(w is None and r!='off_reference' for w,_,r in verdicts),
                         recall=len(hits)/len(want) if want else None))
    for row in rows:
        if row['issued'] != sum(row[k] for k in ('recovered','duplicate_matches','off_reference','rejected')):
            raise ValueError('incomplete per-Run proposal accounting')
        if control and row['recovered'] != row['teacher_commits']:
            raise ValueError('teacher control did not reach full recall')
    transport = {k:execution[k] for k in ('receipt_batches','receipt_counts','wave_receipt_seconds','network_seconds',
                                      'native_verify_seconds','wall_seconds')} if live else {}
    return write_rows(folder,output,rows,transport,rejects,aliased,endings)


def write_rows(folder,output,rows,transport,rejects,aliased,endings):
    output.mkdir(exist_ok=True,parents=True)
    with (output/(folder.name+'.csv')).open('w') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    busy = [r for r in rows if r['teacher_commits']]
    empty = [r for r in rows if not r['teacher_commits']]
    total = sum(r['teacher_commits'] for r in busy)
    found = sum(r['recovered'] for r in busy)
    return dict(live_transport=transport,runs=len(rows),busy=len(busy),empty=len(empty),issued=sum(r['issued'] for r in rows),teacher_commits=total,
                recovered=found,micro=found/total if total else None,
                macro=mean(r['recall'] for r in busy) if busy else None,
                complete_busy=sum(r['recovered']==r['teacher_commits'] for r in busy),
                zero_busy=sum(r['recovered']==0 for r in busy),
                empty_runs_with_proposals=sum(r['issued']>0 for r in empty),
                proposals_on_empty_runs=sum(r['issued'] for r in empty),reasons=rejects,
                duplicates=sum(r['duplicate_matches'] for r in rows),
                recovered_only_by_alternate_certificate=aliased,decode_endings=endings)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('root','binary','weights','output'):
        p.add_argument(key,type=Path)
    p.add_argument('--workloads',nargs='+',required=True)
    p.add_argument('--wave-limit',type=int)
    assists = p.add_mutually_exclusive_group()
    assists.add_argument('--teacher-control',action='store_true')
    assists.add_argument('--oracle-rules',action='store_true')
    p.add_argument('--live-receipts',action='store_true',default=None)
    p.add_argument('--mask-receipts',action='store_true')
    a=p.parse_args()
    torch.set_num_threads(1)
    model = load_actor(a.weights,True)
    if a.live_receipts is None:
        a.live_receipts = getattr(model,'requires_receipts',False) and not (a.teacher_control or a.oracle_rules)
    if a.oracle_rules and (getattr(model,'conditioned_parents',False) or hasattr(model,'generate')):
        p.error('fixed-parent ceiling requires a history-independent parent decoder')
    if a.oracle_rules and a.live_receipts:
        p.error('oracle rules use fixed-snapshot diagnostics')
    if a.mask_receipts and not a.live_receipts:
        p.error('masking requires live receipts')
    if a.wave_limit is None:
        a.wave_limit = getattr(model,'default_waves',1)
    manifest=read(a.root/'manifest.json')
    seeds={r['directory']:r['seed'] for r in manifest}
    report=dict(mode='assist' if a.oracle_rules else 'shadow',oracle_rules=a.oracle_rules,teacher_control=a.teacher_control,live_receipts=a.live_receipts,masked=a.mask_receipts,wave_limit=a.wave_limit,
                weights_sha256=hashlib.sha256(a.weights.read_bytes()).hexdigest(),
                receiver_sha256=hashlib.sha256(a.binary.read_bytes()).hexdigest(), cases={})
    for name in a.workloads:
        report['cases'][name]=audit(a.root/name,a.binary,model,1703+seeds.get(name,0),a.wave_limit,a.output,a.teacher_control,a.live_receipts,a.mask_receipts,a.oracle_rules)
        (a.output/'summary.json').write_text(json.dumps(report,indent=2)+'\n')

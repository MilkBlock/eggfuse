"""One CPU Actor and one exclusive native verifier process, synchronized at actual Run boundaries."""
import argparse
import json
from pathlib import Path
import subprocess
from time import perf_counter

import torch

from rule_read import load_actor
from catalog import Catalog
from history import History


def lane_choice(actor,catalog,memory,state):
    h,rules,logits=state
    action=int(logits.argmax())
    if action == 0:
        return None,None
    rid=rules[action-1]
    refs,_=actor.references(catalog,memory,h,rid)
    return rid,refs


def issue_run(actor, catalog, snapshot, nodes, wave_limit=None):
    """All waves name ports from one sealed snapshot; issued proofs are returned for charging."""
    if wave_limit is None:
        wave_limit = getattr(actor, 'default_waves', 1)
    if wave_limit < 1:
        raise ValueError('a source Run needs at least one wave')
    if hasattr(actor, 'decode'):
        return actor.decode(catalog,snapshot,nodes,wave_limit)
    memory = actor.memory(catalog,snapshot,nodes)
    by_address = {p.address:i for i,p in enumerate(memory.ports)} if wave_limit>1 else {}
    state = [actor.actions(catalog,memory,lane) for lane in range(actor.lanes.num_embeddings)]
    issued, seen = [], set()
    for wave in range(1,wave_limit+1):
        actions, feedback = [], []
        for lane_state in state:
            rid,refs = lane_choice(actor,catalog,memory,lane_state)
            if refs is not None:
                actions.append((rid,refs))
                if wave < wave_limit:
                    embedding = nodes[catalog.roots['generated',rid]]
                    for addr in refs:
                        embedding = actor.next_read(memory.keys[by_address[addr]], embedding)
                    feedback.append(embedding)
        issued.extend(actions)
        if not actions:
            reason = 'stop' if all(int(logits.argmax())==0 for _,_,logits in state) else 'no_complete_request'
            return issued,wave,reason
        if seen.issuperset(actions):
            return issued,wave,'repeated'
        if wave == wave_limit:
            return issued,wave,'budget'
        seen.update(actions)
        summary = torch.stack(feedback).mean(0)
        state = [actor.resume_lane(catalog,memory,h,rules,summary) for h,rules,_ in state]


def propose(actor, catalog, snapshot, nodes):
    return issue_run(actor,catalog,snapshot,nodes)[0]


@torch.no_grad()
def execute(binary, program, actor, seed, wave_limit=None, observe_proposals=None, live_receipts=None, teacher_tape=None, observe_packets=None, mask_receipts=False):
    if wave_limit is None:
        wave_limit = getattr(actor,'default_waves',1)
    if live_receipts is None:
        live_receipts = getattr(actor,'requires_receipts',False)
    start = perf_counter()
    catalog = getattr(actor,'catalog_type',Catalog)(json.loads(program.read_bytes()))
    history = History(catalog,seed)
    before = perf_counter()
    nodes = actor.template_graph(catalog)
    encoding = perf_counter()-before
    next_token = 1
    inference = 0.
    calls = issued = 0
    endings = {}
    receipt_counts = {}
    receipt_seconds = 0.
    if live_receipts and not hasattr(actor, 'decisions'):
        raise ValueError('wave receipts require a sequence actor')
    if teacher_tape and not live_receipts:
        raise ValueError('shadow waves require live receipts')
    role = 'shadow-waves' if teacher_tape else 'online-waves' if live_receipts else 'online'
    cmd = [binary,role,program,teacher_tape or '-','audit']
    with subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1) as p:
        try:
            for line in p.stdout:
                frame = json.loads(line)
                if 'role' in frame:
                    report = frame
                    break
                snapshot = history.snapshot(frame)
                def packets(actions):
                    nonlocal next_token, issued
                    out = []
                    for rid,refs in actions:
                        parents = []
                        for alias,pc in refs:
                            token = history.inverse[alias]
                            row = history.visible[token,pc]
                            parents.append(dict(address=dict(token=token,op=pc),version=row['version']))
                        out.append(dict(run=snapshot.run,rule=rid,parents=parents,token=next_token))
                        next_token += 1
                    issued += len(out)
                    if observe_packets is not None:
                        observe_packets(out)
                    return out

                def send(value):
                    p.stdin.write(json.dumps(value)+'\n')
                    p.stdin.flush()

                def receive(actions):
                    nonlocal receipt_seconds
                    t = perf_counter()
                    out = packets(actions)
                    send(dict(finish=False,requests=out))
                    reply = json.loads(p.stdout.readline())
                    pairs = reply['verdicts']
                    if reply['run'] != snapshot.run or [k for k,_ in pairs] != [x['token'] for x in out]:
                        raise ValueError('out-of-order wave receipt')
                    for _,reason in pairs:
                        receipt_counts[reason] = receipt_counts.get(reason,0)+1
                    receipt_seconds += perf_counter()-t
                    return ['unknown' if mask_receipts else reason for _,reason in pairs]

                before = perf_counter()
                old_wait = receipt_seconds
                if live_receipts:
                    proposals,waves,reason = actor.decode(catalog,snapshot,nodes,wave_limit,receive)
                else:
                    proposals,waves,reason = issue_run(actor,catalog,snapshot,nodes,wave_limit)
                inference += perf_counter()-before-(receipt_seconds-old_wait)
                endings[reason] = endings.get(reason,0)+1
                calls += waves
                if observe_proposals is not None:
                    observe_proposals(snapshot.run, proposals)
                send(dict(finish=True,requests=[]) if live_receipts else packets(proposals))
            else:
                raise RuntimeError('native verifier exited without a final report')
        finally:
            p.stdin.close()
            if 'report' not in locals():
                p.kill()
        if p.wait() or not calls or not report['counts']['calls']:
            raise RuntimeError('empty or unsuccessful online run')
    counts = report['wave_checks'] if teacher_tape else report['counts']
    if report['unused'] or issued != counts['accepted'] + counts['duplicates'] + sum(counts['rejected'].values()):
        raise RuntimeError('unaccounted online proposals')
    if live_receipts and (report['wave_requests'] != issued
            or receipt_counts.get('accepted',0) != counts['accepted']
            or receipt_counts.get('duplicate',0) != counts['duplicates']
            or {r:n for r,n in receipt_counts.items() if r not in ('accepted','duplicate')} != counts['rejected']):
        raise ValueError('wave receipts differ from final verifier ledger')
    return dict(shadow_report=report if teacher_tape else None,live_receipts=live_receipts,receipt_counts=receipt_counts,wave_receipt_seconds=receipt_seconds,
                receipt_batches=report.get('wave_batches',0),mode='shadow' if teacher_tape else 'exclusive',wave_limit=wave_limit,wave_endings=endings,state_sha=report['state_sha'],runs=report['runs'],neural_waves=calls,
                issued=issued,counts=report['counts'],native_runtime_events=len(report['runtime_events']),
                independent_search_calls=0,network_seconds=inference+encoding,
                rhs_by_run=report['rhs'],writes_by_run=report['writes'],source_schedule=report['schedule'],
                remaining_process_seconds_including_ipc=report['seconds']-report['verify_seconds']-inference,
                native_verify_seconds=report['verify_seconds'],native_repair_seconds=report['repair_phase_seconds'],
                wall_seconds=perf_counter()-start)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary',type=Path)
    parser.add_argument('program',type=Path)
    parser.add_argument('--weights',type=Path)
    parser.add_argument('--seed',type=int,default=1703)
    parser.add_argument('--field-pointer',action='store_true')
    parser.add_argument('--wave-limit',type=int)
    parser.add_argument('--live-receipts',action='store_true',default=None)
    a=parser.parse_args()
    torch.set_num_threads(1)
    torch.manual_seed(a.seed)
    model = load_actor(a.weights, a.field_pointer)
    print(json.dumps(execute(a.binary.resolve(),a.program.resolve(),model,a.seed,a.wave_limit,live_receipts=a.live_receipts)))

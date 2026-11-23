"""One CPU Actor and one exclusive native verifier process, synchronized at actual Run boundaries."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryFile
from time import perf_counter

import torch

from rule_read import load_actor
from catalog import Catalog
from history import History


class SourcePanic(RuntimeError):
    def __init__(self,run,charged):
        super().__init__(f'native source panic after issuance in Run {run}')
        self.run=run
        self.charged=charged


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
def execute(binary, program, actor, seed, wave_limit=None, observe_proposals=None, live_receipts=None, teacher_tape=None, observe_packets=None, mask_receipts=False, prefix_policy=None, shadow_runs=None, run_limit=None, observe_snapshot=None, assist=False, audit=True, frame_observer=None, rule_screen=None, activation_observer=None, project_ports=None, higher_catalog=None, higher_choices=None, omit_rules=(), higher_ownership=None, audit_ept=False, side_pointer=None):
    if wave_limit is None:
        wave_limit = getattr(actor,'default_waves',1)
    if live_receipts is None:
        live_receipts = getattr(actor,'requires_receipts',False)
    start = perf_counter()
    catalog = getattr(actor,'catalog_type',Catalog)(json.loads(program.read_bytes()))
    port_projection = None
    if project_ports is None and prefix_policy is not None:
        from anchor_set import OpaqueParentActor
        project_ports = type(actor) is OpaqueParentActor
    if project_ports:
        from addressable_ports import AddressablePorts
        from anchor_set import OpaqueParentActor
        if type(actor) is not OpaqueParentActor or prefix_policy is None:
            raise ValueError('projected encoding requires a bounded port-local pointer model')
        port_projection = AddressablePorts(catalog)
    history = History(catalog,seed,cache_ports=project_ports)
    before = perf_counter()
    nodes = actor.template_graph(catalog)
    encoding = perf_counter()-before
    next_token = 1
    side_seconds = 0.
    inference = 0.
    calls = issued = 0
    endings = {}
    receipt_counts = {}
    receipt_seconds = 0.
    prefix_counts = defaultdict(Counter)
    if prefix_policy is not None:
        from prefix_policy import generate, native_probe
        if not hasattr(actor, 'pair_components') or wave_limit != 1:
            raise ValueError('bounded prefix decoding needs a one-batch anchor Actor')
        live_receipts = bool(teacher_tape or prefix_policy.verify or prefix_policy.audit)
    if shadow_runs is not None and (not teacher_tape or prefix_policy is None):
        raise ValueError('selective inference is a teacher-shadow diagnostic')
    if live_receipts and prefix_policy is None and not hasattr(actor, 'decisions'):
        raise ValueError('wave receipts require a sequence actor')
    if teacher_tape and not live_receipts:
        raise ValueError('shadow waves require live receipts')
    role = 'shadow-waves' if teacher_tape else 'online-waves' if live_receipts else 'online'
    if assist:
        if teacher_tape or live_receipts or prefix_policy is None:
            raise ValueError('assist uses one bounded issuance on each actual source snapshot')
        role = 'assist'
    cmd = [binary,role,program,teacher_tape or '-','audit' if audit else 'time']
    if run_limit is not None:
        cmd.append(str(run_limit))
    if higher_catalog is not None:
        if role not in ('online','assist') or not higher_choices:
            raise ValueError('higher templates require a bounded live Actor and a nonempty catalog')
        cmd.extend(['--higher',higher_catalog])
    if audit_ept:
        cmd.append('--ept')
    with TemporaryFile(mode='w+') as errors, subprocess.Popen(
            cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,text=True,bufsize=1) as p:
        try:
            for line in p.stdout:
                frame = json.loads(line)
                if 'role' in frame:
                    report = frame
                    break
                if frame_observer is not None:
                    frame_observer(frame)
                if rule_screen is not None:
                    rule_screen.history.observe(frame)
                snapshot = history.snapshot(frame)
                if observe_snapshot is not None:
                    observe_snapshot(catalog,history,snapshot)
                owned = higher_ownership.advance(frame,history) if higher_ownership else ()
                def packets(actions):
                    nonlocal next_token, issued, side_seconds
                    out = []
                    for rid,refs in actions:
                        parents = []
                        for alias,pc in refs:
                            token = history.inverse[alias]
                            row = history.visible[token,pc]
                            parents.append(dict(address=dict(token=token,op=pc),version=row['version']))
                        proposal=dict(run=snapshot.run,rule=rid,parents=parents,token=next_token)
                        if higher_choices and rid in higher_choices:
                            proposal['unit'] = higher_choices[rid]
                        if side_pointer is not None:
                            side_start = perf_counter()
                            side_pointer.choose(proposal,history,snapshot)
                            side_seconds += perf_counter()-side_start
                        if higher_ownership and 'unit' not in proposal and higher_ownership.covered(owned,rid,parents):
                            next_token += 1
                            continue
                        out.append(proposal)
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
                if prefix_policy is not None:
                    if shadow_runs is None or snapshot.run in shadow_runs:
                        selected = rule_screen.select(catalog,snapshot,nodes) if rule_screen is not None else None
                        if omit_rules:
                            selected = set(snapshot.rules if selected is None else selected).difference(omit_rules)
                        query_snapshot = port_projection.project(snapshot) if port_projection else snapshot
                        mem = actor.memory(catalog,query_snapshot,nodes) if selected is None or selected else None
                        def read_prefix(rid, roles, rows):
                            nonlocal receipt_seconds
                            start = perf_counter()
                            probe = native_probe(history,query_snapshot,send,lambda: json.loads(p.stdout.readline()))
                            flags = probe(rid, roles, rows)
                            receipt_seconds += perf_counter()-start
                            return flags
                        activated = set() if activation_observer is not None else None
                        proposals = list(generate(actor,catalog,mem,prefix_policy,read_prefix,prefix_counts,
                                                  selected_rules=selected,activated=activated)) if mem is not None else []
                        if activation_observer is not None:
                            activation_observer(snapshot.run, activated)
                        if live_receipts and proposals:
                            receive(proposals)
                        waves,reason = 1,'single_batch'
                    else:
                        proposals,waves,reason = [],0,'outside_shadow_diagnostic'
                elif live_receipts:
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
                code=p.wait()
                errors.seek(0)
                detail=errors.read().strip()
                if code and detail=='Error: "source panic"':
                    raise SourcePanic(history.run,dict(issued=issued,neural_waves=calls,
                        wall_seconds=perf_counter()-start,network_seconds=inference+encoding+side_seconds))
                raise RuntimeError(f'native verifier exited without a final report ({code}): {detail}')
        finally:
            p.stdin.close()
            if 'report' not in locals():
                p.kill()
        if p.wait() or not calls or not report['counts']['calls']:
            raise RuntimeError('empty or unsuccessful online run')
    counts = report['wave_checks'] if teacher_tape else report['counts']
    higher = report.get('higher')
    internal = higher['counts']['issued_steps'] if higher else 0
    if report['unused'] or issued + internal != counts['accepted'] + counts['duplicates'] + sum(counts['rejected'].values()):
        raise RuntimeError('unaccounted online proposals')
    if live_receipts and (report['wave_requests'] != issued
            or receipt_counts.get('accepted',0) != counts['accepted']
            or receipt_counts.get('duplicate',0) != counts['duplicates']
            or {r:n for r,n in receipt_counts.items() if r not in ('accepted','duplicate')} != counts['rejected']):
        raise ValueError('wave receipts differ from final verifier ledger')
    if assist and report['assist']['residual_commits'] + counts['accepted'] != report['matches']:
        raise ValueError('assist ownership differs from committed source bindings')
    return dict(**({'side_pointer':dict(side_pointer.counts),'side_seconds':side_seconds} if side_pointer else {}), **({'ept':report['ept']} if audit_ept else {}), **({'higher':higher,'withheld_owned_requests':higher_ownership.omitted if higher_ownership else 0} if higher else {}), **(dict(visible_port_visits=port_projection.full,encoded_port_visits=port_projection.encoded) if port_projection else {}),
                **(dict(assist=report['assist'],resume_audit=report.get('resumes',[]),event_audit=report.get('events',[])) if assist else {}),partial_proof_counts={f'{kind}_{depth}': dict(c) for (kind,depth),c in prefix_counts.items()},
                native_partial_reads=report.get('prefix_reads',0),native_partial_probes=report.get('prefixes_checked',0),
                native_partial_seconds=report.get('prefix_verify_seconds',0),
                shadow_report=report if teacher_tape else None,live_receipts=live_receipts,receipt_counts=receipt_counts,wave_receipt_seconds=receipt_seconds,
                receipt_batches=report.get('wave_batches',0),mode='assist' if assist else 'shadow' if teacher_tape else 'exclusive',wave_limit=wave_limit,wave_endings=endings,state_sha=report['state_sha'],runs=report['runs'],neural_waves=calls,
                issued=issued,counts=report['counts'],native_runtime_events=len(report['runtime_events']),
                independent_search_calls=report['assist']['exact_rule_calls'] if assist else 0,network_seconds=inference+encoding+side_seconds,
                rhs_by_run=report.get('rhs',[]),writes_by_run=report.get('writes',[]),source_schedule=report['schedule'],
                remaining_process_seconds_including_ipc=report['seconds']-report['verify_seconds']-inference-side_seconds,
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
    parser.add_argument('--top-k', type=int, help='cap the frontier for each rule and owner at every depth')
    parser.add_argument('--verify-prefix',action='store_true',help='check proposed partial proofs before extension')
    parser.add_argument('--assist',action='store_true',help='enable exact residual search in the source executor')
    parser.add_argument('--project-ports',action=argparse.BooleanOptionalAction,default=None)
    a=parser.parse_args()
    from prefix_policy import Policy
    policy=Policy(a.top_k,a.verify_prefix) if a.top_k is not None or a.verify_prefix else None
    torch.set_num_threads(1)
    torch.manual_seed(a.seed)
    model = load_actor(a.weights, a.field_pointer)
    print(json.dumps(execute(a.binary.resolve(),a.program.resolve(),model,a.seed,a.wave_limit,live_receipts=a.live_receipts,prefix_policy=policy,assist=a.assist,project_ports=a.project_ports)))

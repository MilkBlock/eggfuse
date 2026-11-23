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


def issue_run(actor, catalog, snapshot, nodes, wave_limit=1):
    """All waves name ports from one sealed snapshot; issued proofs are returned for charging."""
    if wave_limit < 1:
        raise ValueError('a source Run needs at least one wave')
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
def execute(binary, program, actor, seed, wave_limit=1, observe_proposals=None):
    start = perf_counter()
    catalog = Catalog(json.loads(program.read_bytes()))
    history = History(catalog,seed)
    before = perf_counter()
    nodes = actor.template_graph(catalog)
    encoding = perf_counter()-before
    next_token = 1
    inference = 0.
    calls = issued = 0
    endings = {}
    cmd = [binary,'online',program,'-','audit']
    with subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1) as p:
        try:
            for line in p.stdout:
                frame = json.loads(line)
                if 'role' in frame:
                    report = frame
                    break
                snapshot = history.snapshot(frame)
                before = perf_counter()
                proposals,waves,reason = issue_run(actor,catalog,snapshot,nodes,wave_limit)
                endings[reason] = endings.get(reason,0)+1
                inference += perf_counter()-before
                calls += waves
                out = []
                for rid,refs in proposals:
                    parents = []
                    for alias,pc in refs:
                        token = history.inverse[alias]
                        row = history.visible[token,pc]
                        parents.append(dict(address=dict(token=token,op=pc),version=row['version']))
                    out.append(dict(run=snapshot.run,rule=rid,parents=parents,token=next_token))
                    next_token += 1
                if observe_proposals is not None:
                    observe_proposals(snapshot.run, proposals)
                issued += len(out)
                p.stdin.write(json.dumps(out)+'\n')
                p.stdin.flush()
            else:
                raise RuntimeError('native verifier exited without a final report')
        finally:
            p.stdin.close()
            if 'report' not in locals():
                p.kill()
        if p.wait() or not calls or not report['counts']['calls']:
            raise RuntimeError('empty or unsuccessful online run')
    counts = report['counts']
    if report['unused'] or issued != counts['accepted'] + counts['duplicates'] + sum(counts['rejected'].values()):
        raise RuntimeError('unaccounted online proposals')
    return dict(mode='exclusive',wave_limit=wave_limit,wave_endings=endings,state_sha=report['state_sha'],runs=report['runs'],neural_waves=calls,
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
    parser.add_argument('--wave-limit',type=int,default=1)
    a=parser.parse_args()
    torch.set_num_threads(1)
    torch.manual_seed(a.seed)
    model = load_actor(a.weights, a.field_pointer)
    print(json.dumps(execute(a.binary.resolve(),a.program.resolve(),model,a.seed,a.wave_limit)))

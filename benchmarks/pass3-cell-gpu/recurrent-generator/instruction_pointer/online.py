"""One CPU Actor and one exclusive native verifier process, synchronized at actual Run boundaries."""
import argparse
import json
from pathlib import Path
import subprocess
from time import perf_counter

import torch

from actor import InstructionActor
from catalog import Catalog
from history import History


def propose(actor, catalog, snapshot, nodes):
    memory = actor.memory(catalog,snapshot,nodes)
    proposals = []
    for lane in range(actor.lanes.num_embeddings):
        h, rules, logits = actor.actions(catalog,memory,lane)
        action = int(logits.argmax())
        if action:
            rid = rules[action-1]
            refs,_ = actor.references(catalog,memory,h,rid)
            if refs is not None:
                proposals.append((rid,refs))
    return proposals


@torch.no_grad()
def execute(binary, program, actor, seed):
    start = perf_counter()
    catalog = Catalog(json.loads(program.read_bytes()))
    history = History(catalog,seed)
    before = perf_counter()
    nodes = actor.template_graph(catalog)
    encoding = perf_counter()-before
    next_token = 1
    inference = 0.
    calls = issued = 0
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
                proposals = propose(actor,catalog,snapshot,nodes)
                inference += perf_counter()-before
                calls += 1
                out = []
                for rid,refs in proposals:
                    parents = []
                    for alias,pc in refs:
                        token = history.inverse[alias]
                        row = history.visible[token,pc]
                        parents.append(dict(address=dict(token=token,op=pc),version=row['version']))
                    out.append(dict(run=snapshot.run,rule=rid,parents=parents,token=next_token))
                    next_token += 1
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
    return dict(mode='exclusive',state_sha=report['state_sha'],runs=report['runs'],neural_waves=calls,
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
    a=parser.parse_args()
    torch.set_num_threads(1)
    torch.manual_seed(a.seed)
    model=InstructionActor().eval()
    if a.weights:
        model.load_state_dict(torch.load(a.weights,map_location='cpu',weights_only=True))
    print(json.dumps(execute(a.binary.resolve(),a.program.resolve(),model,a.seed)))

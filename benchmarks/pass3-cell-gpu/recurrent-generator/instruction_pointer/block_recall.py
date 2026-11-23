"""Score all single-batch proposals in bounded replay blocks on the same teacher trajectory."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from time import perf_counter

import torch

from anchor_set_audit import check
from history import History
from rule_read import load_actor
from run_recall import write_rows


@torch.no_grad()
def audit(folder,receiver,model,seed,out,block_size):
    cat=model.catalog_type(json.loads((folder/'program.json').read_bytes()))
    tape=json.loads((folder/'tape.json').read_bytes())
    expected={p['token']:p for p in tape['requests']}
    if len(expected)!=len(tape['requests']):raise ValueError('nonunique teacher token')
    hist=History(cat,seed)
    found=defaultdict(set)
    canonical=set()
    tally=defaultdict(Counter)
    rejects=Counter()
    packets=[]
    blocks=0
    verify_seconds=0.
    block_seconds=0.
    started=perf_counter()
    nodes=model.template_graph(cat)

    def flush():
        nonlocal blocks,verify_seconds,block_seconds
        t=perf_counter()
        native=check(folder,receiver,tape,packets)
        accepted=native['recall_verdicts']
        ids=set()
        for run,token,w,reason in accepted:
            if token<1 or token>len(packets) or token in ids:
                raise ValueError('unexpected verifier receipt')
            ids.add(token)
            p=packets[token-1]
            if p['run']!=run: raise ValueError('cross-Run probe')
            counts=tally[run]
            counts['issued']+=1
            if w is None:
                counts['off_reference' if reason=='off_reference' else 'rejected']+=1
                rejects[reason]+=1
            else:
                target=expected[w]
                if (target['run'],target['rule'])!=(run,p['rule']):raise ValueError('cross-rule credit')
                if p['parents']==target['parents']:canonical.add(w)
                if w in found[run]:counts['duplicate_matches']+=1
                found[run].add(w)
        if len(ids)!=len(packets):raise ValueError('unscored proposal')
        packets.clear()
        blocks+=1
        verify_seconds+=native['verify_seconds']
        block_seconds+=perf_counter()-t

    with (folder/'memory.jsonl').open() as records:
        for line in records:
            frame=hist.snapshot(json.loads(line))
            mem=model.memory(cat,frame,nodes)
            for rid,refs in model.generate(cat,mem):
                parents=[]
                for alias,op in refs:
                    source=hist.inverse[alias]
                    parents.append(dict(address=dict(token=source,op=op),version=hist.visible[source,op]['version']))
                packets.append(dict(token=len(packets)+1,run=frame.run,rule=rid,parents=parents))
                if len(packets)==block_size:flush()
    if packets or not blocks:flush()
    ref=json.loads((folder/'capture.json').read_bytes())
    if len(ref['schedule'])!=hist.run:raise ValueError('incomplete snapshot stream')
    required=Counter(p['run'] for p in expected.values())
    rows=[]
    for run,step in enumerate(ref['schedule'],1):
        n=required[run]
        if n!=step[4]:raise ValueError('incomplete reference')
        count=tally[run]
        h=len(found[run])
        if h+sum(count[k] for k in ('duplicate_matches','off_reference','rejected'))!=count['issued']:
            raise ValueError('incomplete verifier ledger')
        rows.append(dict(run=run,ruleset=step[0],teacher_commits=n,issued=count['issued'],recovered=h,
                         duplicate_matches=count['duplicate_matches'],off_reference=count['off_reference'],
                         rejected=count['rejected'],recall=h/n if n else None))
    elapsed=perf_counter()-started
    times=dict(blocks=blocks,max_packets_per_block=block_size,wall_seconds=elapsed,
               encoding_inference_and_packet_seconds=elapsed-block_seconds,
               probe_and_teacher_replay_wall_seconds=block_seconds,native_reported_verify_seconds=verify_seconds)
    return write_rows(folder,out,rows,times,rejects,sum(map(len,found.values()))-len(canonical),{'single_batch':hist.run})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','binary','weights','out'):p.add_argument(name,type=Path)
    p.add_argument('--workloads',nargs='+',required=True)
    p.add_argument('--block-size',type=int,default=32768)
    a=p.parse_args()
    if a.block_size<1: p.error('positive block size required')
    model=load_actor(a.weights,True)
    torch.set_num_threads(1)
    manifest=json.loads((a.root/'manifest.json').read_bytes())
    seeds={r['directory']:r['seed'] for r in manifest}
    summary=dict(mode='shadow',wave_limit=1,weights_sha256=hashlib.sha256(a.weights.read_bytes()).hexdigest(),
                 receiver_sha256=hashlib.sha256(a.binary.read_bytes()).hexdigest(),cases={})
    for n in a.workloads:
        summary['cases'][n]=audit(a.root/n,a.binary,model,1703+seeds.get(n,0),a.out,a.block_size)
        (a.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')

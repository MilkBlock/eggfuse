"""Measure single-batch recall and conditional tuple quality on identical native snapshots."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random
import subprocess
from tempfile import TemporaryDirectory
from time import perf_counter

import torch

from history import History
from pointer_ranks import ranks
from rule_read import load_actor
from semantic_catalog import SemanticCatalog
from symbol_audit import renamed_program


def data(p):
    return json.loads(p.read_bytes())


def check(folder,binary,tape,requests):
    with TemporaryDirectory() as tmp:
        path=Path(tmp)/'probes.json'
        path.write_text(json.dumps({**tape,'requests':requests}))
        audit=json.loads(subprocess.check_output([binary,'replay',folder/'program.json',folder/'tape.json',
                                                  'audit','--recall',path]))
    capture=folder/'capture.json'
    ref=data(capture) if capture.is_file() else json.loads(subprocess.check_output(
        [binary,'reference',folder/'program.json','-','audit']))
    if (any(audit[k]!=ref[k] for k in ('schedule','writes','rhs','resumes','events','state_sha'))
            or audit['unused'] or audit['unused_recall'] or audit['counts']['accepted']!=len(tape['requests'])
            or len(audit['recall_verdicts'])!=len(requests)):
        raise ValueError('reference trajectory or proposal count changed')
    return audit


@torch.no_grad()
def case(folder,binary,model,seed,runs,rename=None):
    program=data(folder/'program.json')
    cat=SemanticCatalog(program if rename is None else renamed_program(program,rename))
    tape=data(folder/'tape.json')
    teacher=defaultdict(list)
    for p in tape['requests']:
        teacher[p['run']].append(p)
    history=History(cat,seed)
    start=perf_counter()
    nodes=model.template_graph(cat)
    encoding=perf_counter()-start
    proposals={'shadow':[],'given_anchors':[]}
    sec=Counter()
    rows={}
    ranking={}
    with (folder/'memory.jsonl').open() as stream:
        for line in stream:
            raw=json.loads(line)
            snap=history.snapshot(raw)
            if runs is not None and snap.run not in runs:
                continue
            t=perf_counter()
            mem=model.memory(cat,snap,nodes)
            embedding=perf_counter()-t
            labels=[(p['rule'],tuple(history.rename((a['address']['token'],a['address']['op'])) for a in p['parents']))
                          for p in teacher[snap.run]]
            index={p.address:i for i,p in enumerate(snap.ports)}
            anchors=defaultdict(set)
            required=set()
            for packet in teacher[snap.run]:
                rid=packet['rule']
                parents=packet['parents']
                if len(parents)<2: continue
                js=[index[history.rename((a['address']['token'],a['address']['op']))] for a in parents]
                first=next(i for i,j in enumerate(js) if not cat.seminaive[rid] or snap.ports[j].version>=snap.rules[rid])
                anchors[rid,first].add(js[first])
                required.add(packet['token'])
            rows[snap.run]=dict(teacher=len(teacher[snap.run]),multi_parent_teacher=len(required),
                                correct_anchors=sum(map(len,anchors.values())))
            for mode in proposals:
                t=perf_counter()
                actions=model.generate(cat,mem,anchors if mode=='given_anchors' else None)
                issued=proposals[mode]
                for rid,refs in actions:
                    parents=[]
                    for alias,op in refs:
                        token=history.inverse[alias]
                        parents.append(dict(address=dict(token=token,op=op),version=history.visible[token,op]['version']))
                    issued.append(dict(run=snap.run,token=len(issued)+1,rule=rid,parents=parents))
                sec[mode]+=perf_counter()-t+embedding
            ranking[snap.run]=ranks(cat,snap,mem,model,labels)
            if runs is not None and snap.run==max(runs): break
    protocols={}
    for mode,requests in proposals.items():
        t=perf_counter()
        audit=check(folder,binary,tape,requests)
        seconds=perf_counter()-t
        byrun=defaultdict(list)
        for run,token,w,reason in audit['recall_verdicts']:
            if run!=requests[token-1]['run']:raise ValueError('proposal crossed sealed Run')
            byrun[run].append((w,reason))
        total=Counter()
        cases=[]
        for run,row in rows.items():
            required=row['multi_parent_teacher'] if mode=='given_anchors' else row['teacher']
            checked=byrun[run]
            hits={w for w,_ in checked if w is not None}
            matched=sum(w is not None for w,_ in checked)
            rejections=Counter(reason for w,reason in checked if w is None)
            if len(hits)>required: raise ValueError('conditional denominator incorrect')
            cases.append(dict(run=run,required=required,issued=len(checked),hits=len(hits),duplicates=matched-len(hits),
                              other=dict(rejections),recall=len(hits)/required if required else None))
            total.update(required=required,issued=len(checked),recovered=len(hits),duplicates=matched-len(hits),
                         busy=int(required>0),complete_busy=int(0<required==len(hits)),**rejections)
        digest=hashlib.sha256(json.dumps(requests,sort_keys=True).encode()).hexdigest()
        protocols[mode]=dict(counts=dict(total),runs=cases,requests_sha256=digest,encoding_seconds=encoding,network_and_packet_seconds=sec[mode],
            reference_replay_and_probe_wall_seconds=seconds,native_verify_seconds=audit['verify_seconds'],
            proposal_search_calls=0,mode='assist' if mode=='given_anchors' else 'shadow')
    protocols['teacher_prefix_ranks']=ranking
    return protocols


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for field in ('root','binary','weights','out'):p.add_argument(field,type=Path)
    p.add_argument('--case',action='append',required=True)
    p.add_argument('--runs',nargs='+',type=int)
    p.add_argument('--rename',type=int)
    p.add_argument('--fixed-threshold',type=float,help='use this logit cut at every level')
    args=p.parse_args()
    torch.set_num_threads(1)
    model=load_actor(args.weights,True)
    if args.fixed_threshold is not None: model.thresholds.fill_(args.fixed_threshold)
    manifest={r['directory']:r for r in data(args.root/'manifest.json')}
    report=dict(weights_sha256=hashlib.sha256(args.weights.read_bytes()).hexdigest(),
                receiver_sha256=hashlib.sha256(args.binary.read_bytes()).hexdigest(),
                name_mode=model.name_mode,rename=args.rename,thresholds=model.thresholds.tolist(),cases={})
    for name in args.case:
        report['cases'][name]=case(args.root/name,args.binary,model,1703+manifest.get(name,{}).get('seed',0),
                                   set(args.runs) if args.runs else None,args.rename)
        args.out.write_text(json.dumps(report,indent=2)+'\n')

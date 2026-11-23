"""Drive live anchor-led exact completion using the sealed native token ABI."""
import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path
from time import perf_counter
from tempfile import TemporaryFile

import torch

from alternate_proofs import digest
from anchor_set import Domains
from higher_cell import read
from history import History
from prefix_policy import Policy,select_frontier
from prefix_recovery import Recovery
from rule_read import load_actor


@torch.no_grad()
def run(folder,weights,head,binary,mode,historical=False):
    start=perf_counter()
    model=load_actor(weights,True)
    program=read(folder/'program.json')
    cat=model.catalog_type(program)
    nodes=model.template_graph(cat)
    history=History(cat,3434,cache_ports=True)
    policy=Policy(32,recovery=None if historical else Recovery(head,weights))
    positions={r:[i for i,a in enumerate(rule['query']) if 'table' in a['call']]
               for r,rule in enumerate(program['recipe']['rules'])}
    network=perf_counter()-start
    raw_requests=0
    with TemporaryFile() as errors,subprocess.Popen([binary,'anchor-partition',folder/'program.json','-','audit'],
          stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors) as proc:
        try:
            for line in proc.stdout:
                frame=json.loads(line)
                if 'role' in frame:
                    report=frame
                    break
                t=perf_counter()
                req=[]
                if mode=='model':
                    snap=history.snapshot(frame)
                    mem=model.memory(cat,snap,nodes)
                    dom=Domains(mem)
                    for rid in snap.rules:
                        atoms=cat.atoms[rid]
                        for anchor in range(len(atoms) if cat.seminaive[rid] else min(len(atoms),1)):
                            order=cat.read_order(rid,anchor,'source')
                            points=select_frontier(model,cat,mem,dom,rid,anchor,order,0,dom.empty.reshape(1,0),policy,None,Counter(),False)
                            for j in points.flatten().tolist():
                                port=mem.ports[j]
                                token,op=port.address
                                req.append((rid,positions[rid][anchor],dict(address=dict(token=history.inverse[token],op=op),version=port.version)))
                network+=perf_counter()-t
                raw_requests+=len(req)
                proc.stdin.write(json.dumps([frame['run'],req]).encode()+b'\n')
                proc.stdin.flush()
            else:
                errors.seek(0)
                raise RuntimeError(errors.read().decode())
        finally:
            proc.stdin.close()
            if 'report' not in locals():proc.kill()
    if proc.returncode:raise RuntimeError('anchor receiver failed')
    wall=perf_counter()-start
    ref=read(folder/'capture.json')
    for key in ('state_sha','schedule','rhs','writes','resumes','events'):
        if ref[key]!=report[key]:raise ValueError('anchor partition diverged: '+key)
    rows=report['anchor_census']
    table=[r for r in rows if r[2] is not None]
    return dict(mode=mode,program=digest(folder/'program.json'),binary=digest(binary),actor=digest(weights),
                recovery=policy.recovery.checkpoint if policy.recovery else None,wall_seconds=wall,network_seconds=network,requests=raw_requests,
                verify_seconds=report['anchor_verify_seconds'],completion_seconds=sum(r[14] for r in table)*1e-9,
                residual_seconds=sum(r[11]-r[14] for r in table)*1e-9,discovery_seconds=sum(r[10] for r in table)*1e-9,
                source_search_phase_seconds=report['source_search_phase_seconds'],
                selected_point_reads=sum(r[16] for r in table),residual_point_reads=sum(r[15]-r[16] for r in table),
                selected=sum(r[12] for r in table),anchors=sum(r[6] for r in table),
                selected_visits=sum(r[13] for r in table),residual_visits=sum(r[9]-r[13] for r in table),
                selected_commits=sum(r[2] for r in report['anchor_coverage']),required=ref['matches'],
                state_sha=report['state_sha'],source_runs=report['runs'],coverage_by_rule=report['anchor_coverage'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('folder','weights','head','binary','out'):p.add_argument(k,type=Path)
    p.add_argument('--mode',choices=('empty','model'),required=True)
    p.add_argument('--historical',action='store_true')
    a=p.parse_args()
    torch.set_num_threads(1)
    a.out.write_text(json.dumps(run(a.folder,a.weights,a.head,a.binary,a.mode,a.historical))+'\n')

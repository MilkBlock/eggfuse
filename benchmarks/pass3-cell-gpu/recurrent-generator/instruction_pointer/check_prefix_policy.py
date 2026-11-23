"""Regression checks for tile-independent frontier budgets and named-only native partial checks."""
import argparse
import json
from collections import Counter
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import torch

from alternate_proofs import digest
from prefix_policy import Policy, select_frontier


def select(tiles,k):
    # Selection uses one frontier budget across all score tiles.
    batches=[]
    for parent,positions,logits in tiles:
        batches.append((torch.tensor([[parent]]),torch.tensor(positions),torch.tensor([logits])))
    with patch('prefix_policy.score_tiles',return_value=batches):
        kept=select_frontier(SimpleNamespace(thresholds=torch.zeros(3)),None,None,None,0,0,[0,1],1,
                             torch.tensor([[0]]),Policy(k),None,Counter(),False)
    return set(map(tuple,kept.tolist()))


def check_cap():
    tiles=[(0,[0,1,2],[.9,.7,.7]),(1,[3,4,5],[.7,.6,-.5])]
    for batches in (tiles,tiles[::-1]):
        if select(batches,2)!={(0,0)} or len(select(batches,None))!=5:
            raise ValueError('budget crossing a tied score changed with tile order')
        if select(batches,4)!={(0,0),(0,1),(0,2),(1,3)}:
            raise ValueError('an eligible tie fitting within the budget was dropped')


def check_receiver(folder,binary):
    tape=json.loads((folder/'tape.json').read_bytes())
    item=next(p for p in tape['requests'] if len(p['parents'])>=2)
    ref=json.loads((folder/'capture.json').read_bytes())
    tested=0
    cmd=[binary,'shadow-waves',folder/'program.json',folder/'tape.json','audit']
    with subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True) as proc:
        try:
            for line in proc.stdout:
                msg=json.loads(line)
                if 'role' in msg:
                    final=msg
                    break
                if msg['run']==item['run']:
                    a,b=item['parents'][:2]
                    bad_version=dict(b,version=b['version']+1)
                    bad_addr=dict(b,address=dict(token=(1<<62)-1,op=0))
                    for roles,rows in [([0,1],[([a],[b,bad_version,bad_addr])]),([1,0],[([b],[a,dict(a,version=a['version']+1)])])]:
                        probe=dict(run=msg['run'],rule=item['rule'],roles=roles,rows=rows)
                        proc.stdin.write(json.dumps(dict(finish=False,requests=[],prefix_probe=probe))+'\n')
                        proc.stdin.flush()
                        verdict=json.loads(proc.stdout.readline())
                        want=[True]+[False]*(len(rows[0][1])-1)
                        if verdict['prefix_ok']!=[want] or verdict['run']!=msg['run']:
                            raise ValueError('partial proof accepted a stale or unknown address')
                        tested+=len(want)
                proc.stdin.write('{"finish":true,"requests":[]}\n')
                proc.stdin.flush()
        finally:
            proc.stdin.close()
            if 'final' not in locals():
                proc.kill()
    if (proc.returncode or tested!=5 or final['prefixes_checked']!=tested or final['wave_requests']!=0
            or any(final[k]!=ref[k] for k in ('state_sha','schedule','rhs','writes','resumes','events'))):
        raise ValueError('partial checks modified the reference execution')
    return dict(receiver_sha256=digest(binary),checks=tested,reads=final['prefix_reads'],
                issued=final['wave_requests'],state_sha=final['state_sha'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for field in ('folder','binary','out'):p.add_argument(field,type=Path)
    a=p.parse_args()
    check_cap()
    result=check_receiver(a.folder,a.binary)
    a.out.write_text(json.dumps(result,indent=2)+'\n')

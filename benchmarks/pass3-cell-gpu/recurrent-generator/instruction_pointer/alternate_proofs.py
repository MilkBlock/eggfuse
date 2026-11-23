"""Mine offline labels for existing teacher bindings and check each named tuple natively."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from anchor_set_audit import check
from train_anchor_set import training_selection


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def addr(item):
    return item['token'],item['op']


def mine(folder,binary,runs):
    tape=json.loads((folder/'tape.json').read_bytes())
    requests=defaultdict(list)
    for packet in tape['requests']:
        if packet['run'] in runs:
            requests[packet['run']].append(packet)
    visible={}
    probes=[]
    sources=[]
    with (folder/'memory.jsonl').open() as f:
        for line in f:
            frame=json.loads(line)
            for item in frame['retired']:
                del visible[addr(item)]
            for item,row in frame['updates']:
                visible[addr(item)]=row
            run=frame['run']
            if run not in requests: continue
            same_row=defaultdict(list)
            for a,row in visible.items():
                same_row[row['table'],tuple(row['hashes'])].append(a)
            for original in requests[run]:
                for i,p in enumerate(original['parents']):
                    base=addr(p['address'])
                    row=visible[base]
                    if row['version']!=p['version']:
                        raise ValueError('retired teacher witness')
                    for alt in same_row[row['table'],tuple(row['hashes'])]:
                        if alt==base: continue
                        parents=original['parents'].copy()
                        parents[i]=dict(address=dict(token=alt[0],op=alt[1]),version=visible[alt]['version'])
                        probes.append(dict(token=len(probes)+1,run=run,rule=original['rule'],parents=parents))
                        sources.append(original['token'])
    audit=check(folder,binary,tape,probes)
    kept=[]
    counts=Counter(source_commits=sum(map(len,requests.values())),probed=len(probes))
    affected=set()
    for run,t,w,outcome in audit['recall_verdicts']:
        p=probes[t-1]
        if run!=p['run']: raise ValueError('cross-Run label')
        if w!=sources[t-1]:
            counts['different_commit' if w is not None else outcome]+=1
            continue
        kept.append(dict(winner=w,run=run,rule=p['rule'],parents=p['parents']))
        affected.add((run,w))
    counts.update(certificates=len(kept),commits_with_alternative=len(affected))
    return dict(program_sha256=digest(folder/'program.json'),teacher_sha256=digest(folder/'tape.json'),
                memory_sha256=digest(folder/'memory.jsonl'),counts=dict(counts),proofs=kept)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for k in ('root','binary','out'):parser.add_argument(k,type=Path)
    parser.add_argument('--seed',type=int,default=1703)
    a=parser.parse_args()
    result=dict(seed=a.seed,receiver_sha256=digest(a.binary),programs={})
    total=Counter()
    for rec,runs in training_selection(a.root,a.seed):
        name=rec['directory']
        if rec['split']!='train':raise ValueError('only training programs may supply labels')
        result['programs'][name]=mine(a.root/name,a.binary,runs)
        total.update(result['programs'][name]['counts'])
    result['total']=dict(total)
    a.out.write_text(json.dumps(result,separators=(',',':'))+'\n')
    print(total,flush=True)

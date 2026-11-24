"""Offline diagnostic on the first unsealed snapshot; never issue new runtime proofs."""
import argparse,json,subprocess
from collections import Counter,defaultdict
from pathlib import Path
from time import perf_counter
import torch
from event_experiment import frozen
from recursive_rollout import get_policy
from recursive_train import binary,folder,read
from protocol_experiment import dump
from reachability_rollout import ReachStream


def snapshot_at(root,case,rep):
    d=folder(root,case)
    w=root/f'cell-events/admit/{rep}'/(case+'-stream-multi')
    m=read(w/'metrics.json')
    assert m['termination']=='wall_budget'
    by=defaultdict(list)
    for q in read(w/'issued.json')['requests']:by[q['run']].append(q)
    pol=get_policy(root,d,'free','multi');rd=pol.reader
    with subprocess.Popen([binary(root),'online',d/'program.json','-','time'],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE) as proc:
        try:
            for line in proc.stdout:
                f=json.loads(line);rd.advance(f)
                if f['run']==m['runs']+1:
                    return rd,pol.model,f,m
                proc.stdin.write((json.dumps(by[f['run']])+'\n').encode())
                proc.stdin.flush()
        finally:proc.kill()
    raise ValueError("could not reach published prefix")


def count(stream,seconds,weighted=False):
    start=perf_counter()
    if not stream.roles:return dict(full=True,issued=1)
    if not all(stream.roles):return dict(full=True,issued=0)
    multiplicity=[]
    for j,bank in enumerate(stream.roles):
        classes={}
        for a in bank:
            v=stream.rd.store.visible[a]
            key=(tuple(v['hashes']),v['version'],v['forwarded'],min(a[1],64),stream.rd.store.types[a[0]][0]) if weighted else a
            if key not in classes:classes[key]=[a,0]
            classes[key][1]+=1
        reps=sorted(classes.values(),key=lambda pair:-pair[1])
        stream.roles[j]=[a for a,n in reps]
        multiplicity.append(torch.tensor([n for a,n in reps]))
    stream.prepare()
    last=len(stream.roles)-1
    rows=0;total=0;partial=0
    class Incomplete(Exception):pass
    def extend(paths,h,young,j,weights):
        nonlocal rows,total,partial
        if perf_counter()-start>seconds:raise Incomplete
        if j==last:
            if stream.programs(j):raise Incomplete
            if not stream.links[j]:
                n=int(multiplicity[j].sum());fresh=int(multiplicity[j][stream.tables[j][0]].sum())
                n_new=int(weights[young].sum()) if stream.semi else int(weights.sum())
                total+=n*n_new+fresh*(int(weights.sum())-n_new)
            else:
                a,c,col=stream.links[j][0]
                if j not in hist:
                    right=torch.tensor([stream.rd.index.rows[k][2][col] for k in stream.roles[j]])
                    src=torch.tensor([stream.rd.index.rows[k][2][c] for k in stream.roles[a]])
                    hist[j]=(src,torch.zeros(256,dtype=torch.long).scatter_add_(0,right,multiplicity[j]),torch.zeros(256,dtype=torch.long).scatter_add_(0,right,multiplicity[j]*stream.tables[j][0]))
                src,all_b,new_b=hist[j];code=src[paths[:,a]]
                total+=int(((torch.where(young,all_b[code],new_b[code]) if stream.semi else all_b[code])*weights).sum())
            rows+=len(paths);return
        if stream.programs(j):raise Incomplete
        for parent,col in stream.children(paths,j,2048):
            child=torch.cat((paths[parent],col[:,None]),1)
            score,z=stream.score_children(h[parent],j,child,parent)
            keep=score>=0;partial+=len(score)
            if keep.any():extend(child[keep],z[keep],(young[parent]|stream.tables[j][0][col])[keep],j+1,(weights[parent]*multiplicity[j][col])[keep])
    hist={}
    try:
        extend(torch.empty((1,0),dtype=torch.long),stream.model.start(stream.rd.meta(stream.rule))[None,:],torch.tensor([False]),0,torch.ones(1,dtype=torch.long))
        full=True
    except Incomplete:full=False
    return dict(full=full,issued=total,penultimate=rows,partial_scores=partial,seconds=perf_counter()-start)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('root',type=Path);p.add_argument('out',type=Path);p.add_argument('case');p.add_argument('--seconds',type=int,default=15);p.add_argument('--weighted',action='store_true')
    a=p.parse_args();torch.set_num_threads(1);torch.set_grad_enabled(False)
    rd,model,f,m=snapshot_at(a.root,a.case,0)
    g=frozen(a.root,a.case,True)
    result={}
    for rid,wm in f['rules']:
        s=ReachStream(rd,model,rid,wm,Counter(),study=g)
        result[rid]=dict(roles=list(map(len,s.roles)),**count(s,a.seconds,a.weighted))
    dump(a.out/f'cost-bound-{a.case}{"-weighted" if a.weighted else ""}.json',dict(run=f['run'],rules=result,previous_complete=m['runs']))
    print(result,flush=True)

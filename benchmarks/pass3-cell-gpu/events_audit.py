"""Align device-created class names by witnessed constructor applications, after execution."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import struct

import numpy as np
from audit import digest
from codec import canonical


def load(path):return json.loads(path.read_text())


def root(parent,v):
    while v in parent:v=parent[v]
    return v


def align(program,packet,device,oracle,detail,initial_snapshot=None):
    raw=load(program);p=load(packet);gpu=load(device/'run.json')
    if hashlib.sha256(program.read_bytes()).hexdigest()!=p['program_sha256']:
        raise ValueError('offline Cell packet belongs to a different source program')
    image=packet.with_name('device.json')
    if load(image)['packet_sha256']!=hashlib.sha256(packet.read_bytes()).hexdigest() or gpu['packet_sha256']!=hashlib.sha256(image.read_bytes()).hexdigest():
        raise ValueError('device execution and offline Cell packet differ')
    if any(load(folder/'report.json')['program_sha256']!=raw['sha256'] for folder in (oracle,detail)):
        raise ValueError('CPU reference program revision differs')
    cpu=load(detail/'events.json')
    if initial_snapshot is None:
        initial=load(oracle/'binding-audit.json')['initial']
    else:
        initial=load(initial_snapshot)
        if initial['schema']!='eggfuse-repair-inputs/v1' or initial['program_sha256']!=raw['sha256']:
            raise ValueError('repair snapshot belongs to a different program')
    for file in ('rhs.json','writes.json','resumes.json'):
        if (detail/file).read_bytes()!=(oracle/file).read_bytes():
            raise ValueError(f'event collection changed {file}')
    rhs_digest=load(oracle/'rhs.json');writes_digest=load(oracle/'writes.json');resume_digest=load(oracle/'resumes.json')
    anchors={(v['sort'],v['old']):int(v['now'][5:-1]) for v in initial['anchors']}
    origin={p['eq_order'][i]:anchors[v['sort'],v['eq']] for i,v in enumerate(p['symbols']) if 'eq' in v}
    def value(sort,v,parent):
        k=sort['kind'];v=int(v)
        if k=='eq':return {'Eq':root(parent,origin[v])}
        if k=='set':
            ids=sorted(root(parent,origin[int(x)]) for i,x in enumerate(bits) if v&(1<<i))
            if len(ids)!=len(set(ids)):raise ValueError('device event contains duplicated set members')
            return {'Set':[{'Eq':i} for i in ids]}
        if k=='String':return {'Text':gpu['strings'][v]}
        if k=='f64':return {'Float':v}
        return {'Int':v}
    parent={};device_parent={};matrices=[];unresolved=[];details={}
    with np.load(device/'output.npz') as z:
        bits=z.get('set_members',())
        births=z['birth_runs'];cells=z['birth_fields'];table_id=z['meta'][:,0];tables=p['tables']
        functions={}
        for row,tid in enumerate(table_id):
            t=tables[tid]
            if not (t['kind']=='constructor' or t['schema'][-1]['kind']=='Unit' and t['merge_expr'] is None):
                functions[row]=len(functions)
        rhs,writes,unions=z['rhs'],z['writes'],z['unions']
        resumed=z['resumes'] if 'resumes' in z.files else np.empty((0,6),np.int32)
        steps=load(oracle/'report.json')['steps']
        if len(cpu)!=len(steps):raise ValueError('CPU event and source observer counts differ')
        for i,(events,s) in enumerate(zip(cpu,z['runs'])):
            n=i+1;before=parent.copy()
            native_birth=defaultdict(set)
            observed_writes=[];observed_resumes=[]
            for event in events:
                if event[0]=='birth':
                    _,tid,args,out,_,source=event
                    if 'Eq' in out:native_birth[tid,canonical(args),source is None].add(out['Eq'])
                elif event[0]=='union':
                    _,hi,lo=event;parent[hi]=lo
                elif event[0]=='write':observed_writes.append(event[1:])
                elif event[0]=='resume':observed_resumes.append(struct.pack('<5Q',*event[1:]))
            assert [len(observed_writes),digest(observed_writes)]==writes_digest[i]
            assert [len(observed_resumes),hashlib.sha256(b''.join(observed_resumes)).hexdigest()]==resume_digest[i]
            for row in np.flatnonzero(np.abs(births)==n):
                tid=table_id[row];t=tables[tid]
                if t['kind']!='constructor':continue
                schema=t['schema'];output=int(cells[row,len(schema)-1])
                if output in origin:continue
                hits=set()
                for context in ((before,) if births[row]>0 else (before,parent)):
                    try:
                        args=[value(s,v,context) for s,v in zip(schema[:-1],cells[row])]
                    except KeyError:continue
                    hits.update(native_birth.get((int(tid),canonical(args),births[row]<0),()))
                if len(hits)==1:origin[output]=hits.pop()
                else:unresolved.append([n,int(row),t['name'],len(hits)])
            for _,_,hi,lo in unions[unions[:,0]==n]:
                device_parent[int(hi)]=int(lo)
            correct_rule=gpu['sets'][int(s[0])]==steps[i]['ruleset']
            actual_rhs=[];actual_write=[];unmapped_rhs=unmapped_write=0
            for token in rhs[rhs[:,0]==n]:
                rid=int(token[1]);values={}
                try:
                    for j,slot in enumerate(p['rules'][rid]['inputs']):
                        values[str(slot)]=value(raw['recipe']['rules'][rid]['slots'][slot]['sort'],token[4+j],before)
                except KeyError:unmapped_rhs+=1
                actual_rhs.append([rid,values])
            for w in writes[writes[:,0]==n]:
                rid,tid,row=map(int,w[1:4]);schema=tables[tid]['schema']
                context=before if rid>=0 else parent
                try:
                    args=[value(s,v,context) for s,v in zip(schema,w[4:])]
                    old=value(schema[-1],w[-2],context) if w[-3] else None
                    actual_write.append([n,[int(w[-1]),rid] if rid>=0 else None,tid,functions[row],args[:-1],old,args[-1]])
                except KeyError:
                    unmapped_write+=1;actual_write.append(None)
            rhs_ok=not unmapped_rhs and digest(actual_rhs)==rhs_digest[i]
            writes_ok=not unmapped_write and actual_write==observed_writes
            roots={(root(device_parent,v),root(parent,c)) for v,c in origin.items()}
            union_ok=(not unresolved and len(roots)==len({v for v,_ in roots})==len({v for _,v in roots}))
            events_gpu=resumed[resumed[:,0]==n]
            gpu_hash=hashlib.sha256(b''.join(struct.pack('<5Q',*map(int,row[1:])) for row in events_gpu)).hexdigest()
            spine_ok=[len(events_gpu),gpu_hash]==resume_digest[i]
            if not writes_ok and 'write' not in details:
                at=next((j for j,(a,b) in enumerate(zip(actual_write,observed_writes)) if a!=b),min(len(actual_write),len(observed_writes)))
                details['write']=dict(run=n,index=at,device=actual_write[at] if at<len(actual_write) else None,
                                      reference=observed_writes[at] if at<len(observed_writes) else None)
            matrices.append(dict(run=n,schedule=correct_rule and bool(s[3])==steps[i]['changed'],rhs=rhs_ok,
                writes=writes_ok,spine=spine_ok,known_class_roots=union_ok,unknown_rhs=unmapped_rhs,
                unknown_write=unmapped_write,write_count=len(actual_write)==len(observed_writes)))
    keys=('schedule','rhs','writes','spine','known_class_roots','write_count')
    provenance={str(path.name):hashlib.sha256(path.read_bytes()).hexdigest() for path in
                (program,packet,device/'output.npz',oracle/'rhs.json',oracle/'writes.json',oracle/'resumes.json',detail/'events.json')}
    if initial_snapshot is not None:provenance['initial_snapshot']=hashlib.sha256(initial_snapshot.read_bytes()).hexdigest()
    return dict(provenance=provenance,source_runs=len(cpu),device_runs=gpu['completed'],compared=len(matrices),mapped_classes=len(origin),
                unmapped_birth_count=len(unresolved),unmapped_sample=unresolved[:5],first_difference=details,
                aligned_by_ordinal={k:sum(r[k] for r in matrices) for k in keys},
                first_bad={k:next((r['run'] for r in matrices if not r[k]),None) for k in keys},runs=matrices)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('program','packet','device','oracle','detail','out'):p.add_argument(k,type=Path)
    a=p.parse_args();r=align(a.program,a.packet,a.device,a.oracle,a.detail)
    a.out.write_text(json.dumps(r,separators=(',',':'))+'\n')
    print(r['first_bad'],r['unmapped_sample'],r['first_difference'])

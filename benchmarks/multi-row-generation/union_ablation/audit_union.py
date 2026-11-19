"""CPU replay of actual GPU reads against archived Rust Cell CPU partitions."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

HERE=Path(__file__).resolve().parent
CORPUS=HERE.parent/'eclass_ablation'
sys.path.insert(0,str(CORPUS))
from data import dataset
from data.runtime import partition_record

SCHEDULES={'finish':(0,3),'after_locals':(0,2,3),'each':(0,1,2,3)}
POLICIES=('immediate','fenced','fused_fenced','late','stale_negative','no_congruence')
STATS=('receipts','nonempty_flushes','explicit_merges','epochs','repair_passes','signature_checks',
       'congruence_merges','expired_negatives','awakened','max_queue','cached_misses','class_reads')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def truth(data,tick):
    graphs=len(data['a']);template=data['template']
    cls=np.zeros((graphs,6,6),bool);legal=np.zeros((graphs,4),bool)
    secondary=np.zeros_like(legal)
    expected=np.zeros((graphs,4,5),np.int32)
    for i in range(graphs):
        a,ap=data['a'][i],data['a_port'][i]
        events=data['committed'][i].copy() & (data['phase'][i]>=1)
        if tick<2:events[1]=0
        if tick<1:events[0]=0
        phase=np.full(2,int(events.any()),np.int32)
        ext=data['external'][i] if tick==3 else np.zeros(5,np.int32)
        partition,extra,_=partition_record(template,a,ap,phase,events,ext)
        endpoints={(int(v[0]),int(p)):tuple(map(int,v[:2])) for v,p in zip(a,ap)}
        public=[endpoints[o,p] for o in (0,1) for p in template['public_ports']]
        cls[i]=[[v in partition[u] for v in public] for u in public]
        # Remove secondary constructor consequences only for the direct-path diagnostic.
        direct={x:{x} for x in public}
        def unite(l,r):
            group=direct[l]|direct[r]
            for v in group:direct[v]=group
        pair=template['certificates'][0]
        for owner,on in enumerate(events):
            if on:unite(endpoints[owner,pair['left_port']],endpoints[owner,pair['right_port']])
        if ext[0]:unite(tuple(ext[1:3]),tuple(ext[3:5]))
        b=data['b'][i]
        for j,req in enumerate(data['requests'][i]):
            origin=tuple(req[2:4]);read=tuple(req[:2])
            legal[i,j]=origin in partition[read]
            secondary[i,j]=legal[i,j] and origin not in direct[read]
            row,=a[(a[:,:2]==origin).all(-1)]
            tag,=b[b[:,0]==origin[0],1]
            expected[i,j]=[*origin,req[4],row[3],tag]
    return cls,legal,expected,secondary


def check(name,stored,ref,first):
    ticks=SCHEDULES[name]
    batch=len(first['rows']);g=np.arange(batch)[:,None]
    previous=np.zeros((batch,4),bool)
    all_ok=np.ones(batch,bool)
    totals=Counter(graphs=batch);snapshot_counts={}
    for tick in ticks:
        cls,legal,expected,secondary=ref[tick]
        def field(k):return stored[f'{tick}_{k}']
        labels=field('classes')
        partition=(labels[:,:,None]==labels[:,None,:])
        partition_ok=(partition==cls).all((1,2))
        decision=field('legality').astype(bool);active=field('active').astype(bool)
        deltas=legal & ~previous
        delta_ok=(field('delta')==deltas).all(1)
        ptr=field('published_refs');physical=ptr[...,0]
        used=field('published').astype(bool)
        safe=np.clip(physical,0,first['rows'].shape[1]-1)
        source=first['rows'][g,safe]
        witness=((physical==safe)&(first['active'][g,safe]==1)&(ptr[...,1]==np.arange(4))&
                 (source[...,:2]==expected[...,:2]).all(-1)&(source[...,3:]==expected[...,3:]).all(-1))
        row_ok=(field('published_rows')==expected).all(-1)
        visible_ok=((used==legal)&(~used|(witness & row_ok))).all(1)
        read_ptr=field('pointers')
        actual_read=(read_ptr==ptr).all(-1)&(field('rows')==expected).all(-1)
        rhs_ok=((active==legal)&(~active|(actual_read&witness))).all(1)
        ok=partition_ok & visible_ok & rhs_ok & delta_ok & (decision==legal).all(1)
        all_ok &= ok
        snapshot_counts[tick]=int(ok.sum())
        totals.update(observations=batch,partition_errors=int((~partition_ok).sum()),
                      legal_reads=int(legal.sum()),missed_reads=int((legal&~active).sum()),
                      illegal_reads=int((~legal&active).sum()),wrong_deltas=int((~delta_ok).sum()),
                      wrong_witnesses=int((used&~witness).sum()))
        if tick==3:
            totals.update(final_exact=int(visible_ok.sum()),final_partition_exact=int(partition_ok.sum()),
                          final_observation_exact=int(ok.sum()),
                          secondary_required=int(secondary.sum()),secondary_done=int((secondary&active&witness&row_ok).sum()))
        previous=legal
    totals['all_observations_exact']=int(all_ok.sum())
    stats=stored['stats']
    for j,key in enumerate(STATS):
        totals[key]=int(stats[:,j].max() if key=='max_queue' else stats[:,j].sum())
    return totals,snapshot_counts


def merge(into,counts):
    largest=max(into.get('max_queue',0),counts['max_queue'])
    into.update(counts);into['max_queue']=largest


def replay(root,producers,locality,out):
    templates=json.loads((CORPUS/'corpus/manifest.json').read_text())['templates']
    result={}; hashes={}; snapshots={};reproduced=0
    for seed in (1703,1709):
        for t in templates:
            held=t['split']=='heldout'
            if not held and t['id'] not in ('rule-266','rule-267','rule-580'):continue
            name=t['id'];d=dataset('test',t)
            ref={tick:truth(d,tick) for tick in range(4)}
            split='heldout' if held else 'secondary'
            with np.load(locality/'traces'/f"{seed}-{name}-{'original' if held else 'seen-secondary'}.npz") as archived:
                prior={k:archived['first_'+k] for k in ('rows','active','pointers')}
            if held:
                with np.load(producers/'traces'/f'{name}-pairwise-{seed}.npz') as old:
                    for k in prior:np.testing.assert_array_equal(prior[k],old['0_'+k])
            for schedule in SCHEDULES:
                for policy in POLICIES:
                    path=root/'traces'/f'{seed}-{name}-{schedule}-{policy}.npz'
                    hashes[path.name]=digest(path)
                    with np.load(path,allow_pickle=False) as z:
                        first={k:z['first_'+k] for k in prior}
                        for k in first:np.testing.assert_array_equal(first[k],prior[k])
                        counts,observed=check(schedule,z,ref,first)
                    key=f'{seed}/{split}/{schedule}/{policy}'
                    merge(result.setdefault(key,Counter()),counts)
                    snapshots.setdefault(key,Counter()).update(observed)
                    if policy in ('immediate','fenced','fused_fenced') and counts['all_observations_exact']!=len(d['a']):
                        raise ValueError((path,counts,observed))
                    reproduced+=1
    if {p.name for p in (root/'traces').glob('*.npz')}!=set(hashes):raise ValueError('unexamined traces')
    if 'torch' in sys.modules:raise RuntimeError('CPU audit imported PyTorch')
    for seed in (1703,1709):
        for split in ('heldout','secondary'):
            for name in SCHEDULES:
                base=f'{seed}/{split}/{name}'
                if result[base+'/fenced'] != result[base+'/fused_fenced']:
                    raise ValueError('fusing a dispatch changed the counter or source contract')
    out.mkdir(parents=True,exist_ok=True)
    with (out/'metrics.tsv').open('w') as h:
        writer=csv.writer(h,delimiter='\t',lineterminator='\n')
        fields=list(next(iter(result.values())))
        writer.writerow(['seed','panel','observers','mode',*fields])
        for key,r in result.items():writer.writerow([*key.split('/'),*(r[f] for f in fields)])
    times=json.loads((root/'timing.json').read_text())
    (out/'summary.json').write_text(json.dumps(dict(traces=reproduced,plan_sha256=digest(HERE/'plan.json'),
        median_ms=times['medians'],timing_sha256=digest(root/'timing.json'),snapshots=snapshots,
        trace_sha256=hashes),indent=2)+'\n')
    print('Replayed',reproduced,'GPU traces against four observation prefixes')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('root','producers','locality','out'):p.add_argument(name,type=Path)
    a=p.parse_args()
    replay(a.root,a.producers,a.locality,a.out)

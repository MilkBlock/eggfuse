"""Independent CPU queue replay and per-Run comparison with the Rust-backed GPU archive."""
import argparse
from collections import Counter
import csv
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'eclass_ablation'))
from data import dataset

BUDGETS=(1,2,4,8,12,16,24,32,48)
POP=tuple(bin(i).count('1') for i in range(8))
PLANS=json.loads((HERE.parent/'union_ablation/plan.json').read_text())['plans']


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=4096)
def simulate(name,manifest,lane,decisions):
    p=PLANS[name];cls=list(range(p['vertices']));index=cls.copy()
    s=[0]*24;bound=[[-1]*8 for _ in range(2)]
    shapes=[tuple(index),None,None]
    flight=set();inbox=set()
    snapshots=[];rows=[]
    fixed=lane.startswith('fixed');k=int(lane[5:]) if fixed else 1
    learned=not (fixed or lane=='exact')
    def join(a,b):
        x,y=cls[a],cls[b]
        if x==y:return False
        old,new=max(x,y),min(x,y)
        cls[:]=[new if v==old else v for v in cls]
        return True
    for budget in BUDGETS:
        while s[9]<budget and s[0]<2:
            phase=s[0];events=manifest[phase*10:phase*10+10]
            if not s[8]:
                flight={j for j in range(3) if events[j*3]>=0};inbox=set();s[8]=1
            arrived={j for j in flight if events[3*j+2]<=s[1]}
            inbox|=arrived;flight-=arrived
            s[6]=int(events[9]<=s[1])
            ready=bool(inbox or s[4] or s[5])
            safe=not (ready or flight or not s[6])
            ideal=0 if ready else (2 if safe else 1)
            action=decisions[s[9]] if learned else ideal
            blind=lane.startswith('blind')
            rows.append([len(inbox),3*s[4],3*s[5],3*s[7],0 if blind else len(flight),
                         0 if blind else 3*s[6],ideal,action,phase,s[1],int(safe)])
            if learned:s[23]+=1
            if lane.endswith('fair') and ready and action!=0 and s[20]>=2:
                action=0;s[18]+=1
            changed=False
            if action==0 and inbox:
                event=min(inbox);inbox.remove(event);s[10]+=1
                changed=join(*events[event*3:event*3+2])
                if changed:s[4]=s[5]=1
            elif action==0 and s[4]:
                s[11]+=1
                for rule in p['implications']:
                    if all(cls[a]==cls[b] for a,b in rule['requires']):
                        changed=join(*rule['unifies']) or changed
                s[4]=int(changed)
                if changed:s[5]=1
            elif action==0 and s[5]:
                index=cls.copy();s[5]=0;s[12]+=1
            else:s[13]+=1
            s[2]=sum(1<<j for j in flight);s[3]=sum(1<<j for j in inbox)
            s[7]=int(changed)
            if ready and action!=0:
                s[17]+=1;s[20]+=1;s[19]=max(s[19],s[20])
            else:s[20]=0
            s[1]+=1;s[9]+=1
            closed=not (flight or inbox or s[4] or s[5] or not s[6])
            attempt=(s[1]%k==0) if fixed else (closed if lane=='exact' else action==2)
            if attempt:
                s[14]+=1;s[22]+=1
                if not closed and not lane.endswith('raw'):s[15]+=1;continue
                if not closed:s[16]+=1
                shapes[phase+1]=tuple(index)
                bound[phase]=[s[9],s[2],s[3],s[4],s[5],s[6],int(closed),s[1]]
                s[21]+=1;s[0]+=1;s[1:9]=[0]*8;s[20]=0
        snapshots.append((tuple(s),tuple(tuple(v) for v in bound),tuple(shapes)))
    return np.array(rows),snapshots


def source_inputs(d,plan,panel):
    """Construct physical endpoints and the finite delivery contract from the public fixture."""
    n=len(d['a']);manifest=np.full((n,2,10),-1,np.int32)
    addresses=np.empty((n,4,2),np.int32)
    nodes={(o,p):v for o in (0,1) for p,v in zip(plan['ports'],plan['public'][o])}
    for g in range(n):
        bucket=(g+3*(g//8))%16
        manifest[g,:,9]=0
        for owner in (0,1):
            manifest[g,0,owner*3+2]=owner
            if d['phase'][g,owner]>=1 and d['committed'][g,owner]:
                manifest[g,0,3*owner:3*owner+2]=[plan['public'][owner][k] for k in plan['local_pair']]
        ext=d['external'][g]
        if ext[0]:
            manifest[g,1,:2]=[nodes[o,p] for o,p in zip(ext[[1,3]],d['external_ports'][g])]
        if panel=='ordinary':
            manifest[g,1,2]=10 if bucket==0 else 0
            if bucket==1:manifest[g,1,3:5]=plan['public'][0][plan['local_pair'][0]]
            manifest[g,1,5]=10
            if bucket==2:manifest[g,1,9]=10
        else:
            manifest[g,1,2]=10 if panel=='late_union' else 0
            if panel=='late_duplicate':
                manifest[g,1,3:5]=plan['public'][0][plan['local_pair'][0]]
                manifest[g,1,5]=10
            if panel=='late_seal':manifest[g,1,9]=10
        for j,(q,ports) in enumerate(zip(d['requests'][g],d['request_ports'][g])):
            addresses[g,j]=nodes[q[0],ports[0]],nodes[q[2],ports[1]]
    return manifest,addresses


def check_lane(z,lane,name,native,manifest,source,addr):
    # Materialize a batch of independently replayed ledger snapshots for every budget.
    trace=z[lane+'_trace'];n=len(trace);full_ref=np.stack(native,axis=1)
    states=[];boundaries=[];visible_ix=[]
    for g in range(n):
        decisions=tuple(map(int,trace[g,trace[g,:,6]>=0,7])) if not (lane.startswith('fixed') or lane=='exact') else ()
        expected,snap=simulate(name,tuple(map(int,manifest[g].flat)),lane,decisions)
        np.testing.assert_array_equal(trace[g,:len(expected)],expected)
        if not (trace[g,len(expected):]==-1).all():raise ValueError('trace past completion')
        states.append([r[0] for r in snap]);boundaries.append([r[1] for r in snap]);visible_ix.append([r[2] for r in snap])
    states=np.asarray(states);boundaries=np.asarray(boundaries)
    for j,budget in enumerate(BUDGETS):
        state=z[f'{lane}_{budget}_state'];pub=z[f'{lane}_{budget}_visible'];bounds=z[f'{lane}_{budget}_boundary']
        np.testing.assert_array_equal(state,states[:,j]);np.testing.assert_array_equal(bounds,boundaries[:,j])
        # Distinct partitions at already-opened boundaries may be few; compare
        # every published row and original parent, including prematurely opened views.
        for s in range(3):
            ids=[visible_ix[g][j][s] for g in range(n)]
            emitted=np.array([ix is not None for ix in ids])
            np.testing.assert_array_equal(pub[~emitted,s],np.full_like(pub[~emitted,s],-1))
            if emitted.any():
                index=np.asarray([ix for ix in ids if ix is not None])
                gidx=np.arange(len(index))[:,None]
                q=addr[emitted];src=source[emitted].copy()
                ok=(index[gidx,q[...,0]]==index[gidx,q[...,1]])&(src[...,0]>=0)
                src[~ok]=-1
                out=np.concatenate((index[:,sum(PLANS[name]['public'],[])],src.reshape(len(index),-1)),axis=1)
                np.testing.assert_array_equal(pub[emitted,s],out)
        exact=(pub==full_ref).all((1,2))
        done=state[:,0]==2
        safe=done & (state[:,16]==0) & exact
        if not lane.endswith('raw') and np.any(done & ~safe):raise ValueError((lane,budget,'unsound'))
        pending=(~done)
        metrics=Counter(graphs=n,complete=int(safe.sum()),returned_terminal=int(done.sum()),all_public_exact=int(exact.sum()),
            false_saturation=int((done & (state[:,16]>0)).sum()),false_claims=int(state[:,16].sum()),
            false_terminal_correct_views=int((done&(state[:,16]>0)&exact).sum()),suspended=int(pending.sum()),
            remaining_phases=int((2-state[:,0]).sum()),outstanding_sent=int(sum(POP[m] for m in state[:,2])),
            inbox=int(sum(POP[m] for m in state[:,3])),dirty=int(state[:,4].sum()),pending_delta=int(state[:,5].sum()),
            ticks=int(state[:,9].sum()),work=int(state[:,10:13].sum()),receipts=int(state[:,10].sum()),
            passes=int(state[:,11].sum()),propagations=int(state[:,12].sum()),idle=int(state[:,13].sum()),
            veto=int(state[:,15].sum()),forced=int(state[:,18].sum()),observations=int(state[:,21].sum()))
        yield budget,metrics,safe


def main(root,previous,out):
    import statistics
    ts=json.loads((HERE.parent/'eclass_ablation/corpus/manifest.json').read_text())['templates']
    reference=json.loads((HERE.parent/'union_ablation/results/summary.json').read_text())['trace_sha256']
    timing=json.loads((root/'timings.json').read_text());agg={};hashes={};timed={};causal=Counter()
    for seed in (1703,1709):
        for t in ts:
            name=t['id'];split='heldout' if t['split']=='heldout' else 'secondary'
            if split=='secondary' and name not in ('rule-266','rule-267','rule-580'):continue
            d=dataset('test',t)
            old=previous/'traces'/f'{seed}-{name}-each-fenced.npz'
            if sha(old)!=reference[old.name]:raise ValueError(old)
            with np.load(old) as archive:base=dict(archive)
            native=[]
            for tick in (0,2,3):
                src=np.concatenate((base[f'{tick}_pointers'][...,:1],base[f'{tick}_rows']),axis=-1)
                src[~base[f'{tick}_active'].astype(bool)]=-1
                native.append(np.concatenate((base[f'{tick}_classes'],src.reshape(len(src),-1)),axis=1))
            ptr=base['0_pointers'][...,0];g=np.arange(len(ptr))[:,None];picked=base['first_rows'][g,ptr]
            expected_src=np.concatenate((ptr[...,None],picked[...,:2],d['requests'][...,4:5],picked[...,3:]),axis=-1)
            queue_prefix={}
            for panel in ('ordinary','late_union','late_duplicate','late_seal'):
                path=root/'traces'/f'{seed}-{name}-{panel}.npz';hashes[path.name]=sha(path)
                with np.load(path) as archive:
                    manifest,src,addr=(archive[k] for k in ('manifest','source','addresses'))
                    contract,queries=source_inputs(d,PLANS[name],panel)
                    np.testing.assert_array_equal(manifest,contract);np.testing.assert_array_equal(addr,queries)
                    np.testing.assert_array_equal(src,expected_src)
                    for k in ('active','rows','pointers'):np.testing.assert_array_equal(archive['first_'+k],base['first_'+k])
                    lanes=[k[:-6] for k in archive.files if k.endswith('_trace')]
                    for lane in lanes:
                        key=f'{seed}/{split}/{panel}/{lane}'
                        for budget,m,safe in check_lane(archive,lane,name,native,manifest,src,addr):
                            agg.setdefault(f'{key}/{budget}',Counter()).update(m)
                            if budget==48 and key in timing:
                                indices=np.random.default_rng(1919).permutation(len(ptr))[:12]
                                timed[key]=timed.get(key,0)+int(safe[indices].sum())
                        if lane=='exact':
                            # A transport-only change in phase 2 cannot affect phase 1.
                            a=archive['exact_48_boundary'][:,0]
                            if not queue_prefix:queue_prefix['boundary']=a
                            else:np.testing.assert_array_equal(queue_prefix['boundary'],a);causal['phase1_equal_graphs']+=len(a)
            print(seed,name,flush=True)
    assert set(hashes)=={p.name for p in (root/'traces').glob('*.npz')} and len(hashes)==48
    out.mkdir(parents=True,exist_ok=True)
    fields=list(next(iter(agg.values())))
    with (out/'metrics.tsv').open('w') as f:
        w=csv.writer(f,delimiter='\t',lineterminator='\n');w.writerow(['seed','panel','transport','lane','budget',*fields])
        for k,m in agg.items():w.writerow([*k.split('/'),*(m[j] for j in fields)])
    rate={}
    for k,times in timing.items():
        ms=[r[1] for r in times]
        rate[k]=dict(samples=len(ms),completed=timed[k],median_ms=statistics.median(ms),correct_per_second=1000*timed[k]/sum(ms))
    if 'torch' in sys.modules:raise RuntimeError('CPU replay imported torch')
    (out/'summary.json').write_text(json.dumps(dict(timings=rate,trace_hashes=hashes,causal=causal,
        timing_sha256=sha(root/'timings.json'),weights={p.stem:json.loads(p.read_text()) for p in root.glob('*-17*.json')}),indent=1)+'\n')
    print('Verified all queue prefixes, observers and terminal statuses')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('root','previous','out'):p.add_argument(k,type=Path)
    a=p.parse_args();main(a.root,a.previous,a.out)

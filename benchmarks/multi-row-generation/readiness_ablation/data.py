"""Source event streams, held-out schedule families and independent producer/consumer truth."""
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
import argparse
import json
import numpy as np

WAVES=3
KEYS=4
EVENT_SLOTS=16
KINDS=('P0','P1','U')
CONSUMERS=('C','V')
TABLES=KINDS+CONSUMERS
# Missing-open and missing-sealed have identical observations until the final seal.
VARIANTS=('on_time','late','missing_open','missing_sealed')
SIZES={'train':4096,'iid':256,'heldout':512}
SEEDS={'train':707101,'iid':707102,'heldout':707103}


def schedule_family(arrivals):
    # Classify by concurrent chains without using key IDs, values or event positions.
    u_leads=sum(p0==2 and 0<=u<2 for p0,p1,u in arrivals)
    c_leads=sum(0<=p0<2 and 0<=p1<2 and u==2 for p0,p1,u in arrivals)
    return 'two_early_u' if u_leads>=2 else 'two_early_c' if c_leads>=2 else 'mixed_train'


@lru_cache(maxsize=1)
def schedule_banks():
    rng=np.random.default_rng(72056);wanted={'mixed_train':80,'two_early_u':24,'two_early_c':24};banks={k:{} for k in wanted}
    for _ in range(300000):
        # Focal P0@0, U never @2: changing the focal P1 cannot change the family.
        focal=(0,0,int(rng.integers(2)));decoy=(int(rng.integers(3)),0,0)
        tail=rng.integers(3,size=(2,3));tail[rng.random(tail.shape)<.08]=-1
        candidate=(focal,decoy,*map(tuple,tail.tolist()));family=schedule_family(candidate);bank=banks[family]
        if len(bank)<wanted[family]:
            signature=tuple(sorted((p0,(-2 if j==0 else p1),u) for j,(p0,p1,u) in enumerate(candidate)))
            bank.setdefault(signature,candidate)
        if all(len(banks[k])==size for k,size in wanted.items()):break
    if any(len(banks[k])!=size for k,size in wanted.items()):raise ValueError('incomplete schedule bank')
    return {k:list(v.values()) for k,v in banks.items()}


def _validate(events,seal):
    events,seal=np.asarray(events),np.asarray(seal)
    if events.ndim!=4 or events.shape[1:]!=(WAVES,EVENT_SLOTS,3) or events.dtype.kind not in 'iu':
        raise ValueError('events must be integer [B,3,16,3]')
    if seal.shape!=(len(events),3,KEYS) or not np.isin(seal,[0,1]).all():raise ValueError('seal must be binary [B,producer-kind,key]')
    kind,key,value=events.transpose(3,0,1,2)
    if (kind<0).any() or (kind>3).any() or (key<0).any() or (key>=KEYS).any() or (value<0).any() or (value>=8).any():raise ValueError('event outside finite source vocabulary')
    if np.any(events[kind==0]!=0):raise ValueError('padding requires the all-zero event')
    return events,seal.astype(bool)


def _source_rows(events,seal):
    """Serial set interpreter, independent of the tensor ledger in oracle()."""
    visible={name:set() for name in TABLES};first={};runs=[]
    for tick,wave in enumerate(events):
        rhs={name:set() for name in TABLES};arrived=0
        for kind,key,value in wave.tolist():
            if kind==0:continue
            arrived+=1;name=KINDS[kind-1];fact=(key,value);rhs[name].add(fact)
            existing=first.get((kind,key))
            if existing is not None and existing[0]!=value:raise ValueError('conflicting producer payload for key')
            first.setdefault((kind,key),(value,tick))
        writes={name:rhs[name]-visible[name] for name in TABLES}
        for name in TABLES:visible[name].update(writes[name])
        runs.append(dict(ordinal=tick+1,rhs={n:sorted(v) for n,v in rhs.items()},effective_writes={n:sorted(v) for n,v in writes.items()},
                         visible={n:sorted(v) for n,v in visible.items()},transport_events=arrived,transport_duplicates=arrived-sum(map(len,writes.values())),
                         same_wave_retransmissions=arrived-sum(map(len,rhs.values()))))
    rhs={name:set() for name in TABLES};witnesses={'C':{},'V':{}}
    for key,x in visible['P0']:
        for k,y in visible['P1']:
            if k==key:rhs['C'].add((k,x,y));witnesses['C'][k]=[(1,k,x,first[1,k][1]),(2,k,y,first[2,k][1])]
    for k,z in visible['U']:rhs['V'].add((k,z));witnesses['V'][k]=[(3,k,z,first[3,k][1])]
    for name in TABLES:visible[name].update(rhs[name])
    runs.append(dict(ordinal=4,rhs={n:sorted(v) for n,v in rhs.items()},effective_writes={n:sorted(v) for n,v in rhs.items()},
                     visible={n:sorted(v) for n,v in visible.items()},transport_events=0,transport_duplicates=0,same_wave_retransmissions=0))
    status={c:{} for c in CONSUMERS}
    for c,deps in [('C',(1,2)),('V',(3,))]:
        for k in range(KEYS):
            missing=[p for p in deps if (p,k) not in first]
            status[c][k]=('computed' if not missing else 'sealed_absent' if any(seal[p-1,k] for p in missing) else 'pending_open')
    return dict(runs=runs,finish_witnesses=witnesses,terminal_status=status)


def source_rows(events,seal=None):
    """Ordered source Runs. RHS is a set within each wave; a later duplicate is a real RHS again."""
    if seal is None:seal=np.zeros((3,KEYS),bool)
    e,s=_validate(np.asarray(events)[None],np.asarray(seal)[None]);return _source_rows(e[0],s[0])


def oracle(events,seal):
    events,seal=_validate(events,seal);batch=len(events)
    # Earliest visible receipt and source RHS/EW counts. One physical payload per producer/key.
    value=np.full((batch,3,KEYS),-1,np.int32);arrived=np.full_like(value,-1);rhs_count=np.zeros((batch,4,5),np.int32)
    writes=np.zeros_like(rhs_count);row_key=np.arange(KEYS,dtype=np.int32)[None,:]
    for tick in range(WAVES):
        kind,key,payload=events[:,tick].transpose(2,0,1)
        for producer in range(3):
            for k in range(KEYS):
                hits=(kind==producer+1)&(key==k);any_hit=hits.any(-1)
                top=np.where(hits,payload,-1).max(-1);bottom=np.where(hits,payload,8).min(-1)
                seen=arrived[:,producer,k]>=0
                if np.any(any_hit & ((top!=bottom)|(seen & (value[:,producer,k]!=top)))):raise ValueError('two distinct payloads for one producer key')
                new=any_hit & ~seen;arrived[new,producer,k]=tick;value[new,producer,k]=top[new]
                rhs_count[:,tick,producer]+=any_hit.astype(np.int32);writes[:,tick,producer]+=new.astype(np.int32)
    ticks=np.arange(WAVES+1)[None,:,None,None]
    live=(arrived[:,None]>=0)&(arrived[:,None]<=ticks);first=np.where(live,arrived[:,None],-1).astype(np.int32);values=np.where(live,value[:,None],-1).astype(np.int32)
    ready=np.stack((live[:,:,0]&live[:,:,1],live[:,:,2]),axis=2);never=~ready[:,-1]
    ready_tick=np.where(never,-1,ready.argmax(1)).astype(np.int32)
    expected=np.full((batch,4,2,KEYS,3),-1,np.int32)
    expected[:,:,0,:,0]=row_key;expected[:,:,0,:,1]=values[:,:,0];expected[:,:,0,:,2]=values[:,:,1]
    expected[:,:,1,:,0]=row_key;expected[:,:,1,:,1]=values[:,:,2]
    expected[~ready]=-1
    rhs_count[:,3,3:]=ready[:,3].sum(-1);writes[:,3,3:]=rhs_count[:,3,3:]
    absent=(~live[:,-1]) & seal
    sealed=np.stack((absent[:,0]|absent[:,1],absent[:,2]),axis=1)&never
    public=np.zeros_like(ready);public[:,3]=ready[:,3]
    return dict(desired_ready=ready,desired_privately_ready=ready,parent_live=live,parent_value=values,parent_first_tick=first,parent_version=first+1,
                ready_tick=ready_tick,expected_rows=expected,expected_public=public,sealed_absent=sealed,pending_open=never&~sealed,
                source_rhs_count=rhs_count,effective_write_count=writes)


def _group(split,index):
    rng=np.random.default_rng(np.random.SeedSequence([SEEDS[split],index]));banks=schedule_banks()
    family=('two_early_u' if index%2==0 else 'two_early_c') if split=='heldout' else 'mixed_train'
    bank=banks[family];schedule=np.asarray(bank[(index//2 if split=='heldout' else index)%len(bank)],np.int32)
    keys=rng.permutation(KEYS);focal=int(keys[0]);other=int(keys[1]);values=rng.integers(8,size=(KEYS,3),dtype=np.int32)
    values[1,1]=values[0,1];values[0,2]=values[1,2]  # same payload, different physical parent key
    slots=rng.permutation(EVENT_SLOTS);lanes=slots[:KEYS*3].reshape(KEYS,3)
    base=np.zeros((WAVES,EVENT_SLOTS,3),np.int32)
    for i in range(KEYS):
        for j in range(3):
            time=int(schedule[i,j]);
            if time>=0 and (i,j)!=(0,1):base[time,lanes[i,j]]=(j+1,keys[i],values[i,j])
    # Retransmit the same unrelated U in wave 0; resend an already published
    # focal P0 in a later wave. Both paths preserve a single stable fact witness.
    base[0,slots[12]]=(3,other,values[1,2]);base[int(rng.integers(1,3)),slots[13]]=(1,focal,values[0,0])
    flags=rng.integers(2,size=(3,KEYS),dtype=np.int32).astype(bool);flags[1,focal]=False
    records=[]
    for variant,p1_wave in enumerate((0,2,-1,-1)):
        events=base.copy();seal=flags.copy()
        if p1_wave>=0:events[p1_wave,lanes[0,1]]=(2,focal,values[0,1])
        if variant==3:seal[1,focal]=True
        records.append((events,seal,np.int32(focal),np.int32(other),np.int32(index),np.int32(variant),family))
    return records


def dataset(split,count=None):
    """Source group = 4 counterfactuals. Feed events one wave at a time, seal only at finish."""
    if split not in SIZES:raise ValueError(f'unknown split {split}')
    n=SIZES[split] if count is None else int(count)
    if n<=0 or n%4:raise ValueError('size must be a positive multiple of four')
    records=[row for g in range(n//4) for row in _group(split,g)]
    d={k:np.stack(v) for k,v in zip(('events','seal','focal_key','unrelated_key','group_id','variant','family'),zip(*records))}
    truth=oracle(d['events'],d['seal']);d.update(desired_ready=truth['desired_ready'],desired_privately_ready=truth['desired_ready'],split=split)
    return d


def _signature(first):return tuple(sorted(tuple(map(int,x)) for x in first.T))


def freeze():
    digests={};sigs={};payloads={}
    for split in SIZES:
        d=dataset(split);e,seal=d['events'],d['seal'];truth=oracle(e,seal);first=truth['parent_first_tick'][:,-1]
        signatures={_signature(x) for x in first};sigs[split]=signatures
        payloads[split]={sha256(a.tobytes()+s.tobytes()).hexdigest() for a,s in zip(e,seal)}
        assert len(payloads[split])==SIZES[split]
        for i in range(0,len(e),4):
            focus=int(d['focal_key'][i]);other=int(d['unrelated_key'][i]);assert focus!=other
            new=[np.array(x,copy=True) for x in e[i:i+4]]
            for x in new:x[(x[:,:,0]==2)&(x[:,:,1]==focus)]=0
            assert all(np.array_equal(new[0],x) for x in new[1:])
            assert np.array_equal(e[i+2],e[i+3]);assert list(first[i:i+4,1,focus])==[0,2,-1,-1]
            assert list(truth['ready_tick'][i:i+4,0,focus])==[0,2,-1,-1]
            assert (truth['ready_tick'][i:i+4,1,other]==0).all()
            assert truth['pending_open'][i+2,0,focus] and truth['sealed_absent'][i+3,0,focus]
            for z in range(i,i+4):assert schedule_family(first[z].T.tolist())==d['family'][z]
        # Check tensor readiness against a separate set interpreter on *all* graphs.
        for g in range(len(e)):
            q=_source_rows(e[g],seal[g]);
            for time,run in enumerate(q['runs']):
                assert list(map(len,run['rhs'].values()))==truth['source_rhs_count'][g,time].tolist()
                assert list(map(len,run['effective_writes'].values()))==truth['effective_write_count'][g,time].tolist()
                for typ,c in enumerate(CONSUMERS):
                    public=truth['expected_rows'][g,time,typ][truth['expected_public'][g,time,typ]]
                    rows=[tuple(map(int,row[:(3 if typ==0 else 2)])) for row in public]
                    assert sorted(rows)==run['visible'][c]
            for typ,c in enumerate(CONSUMERS):
                assert all(q['terminal_status'][c][k]==('sealed_absent' if truth['sealed_absent'][g,typ,k] else 'pending_open' if truth['pending_open'][g,typ,k] else 'computed') for k in range(KEYS))
        positions=truth['source_rhs_count'].sum((0,));inserts=truth['effective_write_count'].sum(0)
        digests[split]=dict(seed=SEEDS[split],graphs=len(e),counterfactual_groups=len(e)//4,
            families={k:int((d['family']==k).sum()) for k in sorted(set(d['family']))},
            distinct_key_renaming_invariant_schedules=len(signatures),source_rhs_by_run_table=positions.tolist(),effective_writes_by_run_table=inserts.tolist(),
            sha256={k:sha256(d[k].tobytes()).hexdigest() for k in ('events','seal','desired_ready','focal_key','unrelated_key','group_id','variant')})
    assert sigs['iid']<=sigs['train'] and sigs['heldout'].isdisjoint(sigs['train']|sigs['iid'])
    assert all(payloads[a].isdisjoint(payloads[b]) for a,b in [('train','iid'),('train','heldout'),('iid','heldout')])
    return dict(schema='eggfuse.readiness-wave.data/v1',panels=digests,source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                full_schedule_signatures_heldout_train_overlap=0,full_iid_schedules_seen_in_training=True,exact_input_overlap=0)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);opts=p.parse_args();record=freeze()
    if opts.output.exists() and json.loads(opts.output.read_text())!=record:raise ValueError('frozen readiness manifest mismatch')
    if not opts.output.exists():opts.output.write_text(json.dumps(record,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:(v['graphs'],v['families'],v['distinct_key_renaming_invariant_schedules']) for k,v in record['panels'].items()}))

"""Zero-update growth of a Bake library inside the real Pass 3 recurrent generator and verifier."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from statistics import median
from time import perf_counter_ns
from types import SimpleNamespace

import numpy as np
import torch
from policy import read,forced,split
from capture import inputs,load_catalog,execute,verify
from catalog import validate_join_ports
from compound_model import CompoundActor
from score_cost import measure as measure_score
from model import Actor
from feedback_study import bind_session


def cohort(unit,joins,catalog,seen,cold,family):
    pos=next(i for i,j in enumerate(joins) if j[0]==unit)
    if catalog.family[pos]==family:return 'held_left_family'
    if unit in cold:return 'held_combination'
    if pos in seen:return 'seen'
    return 'growth'


def opportunities(folder,entries,compiled):
    with np.load(folder/'neural-inputs.npz') as z,np.load(folder/'output.npz') as g:
        pivot,ticket,publications,features=(z[k] for k in ('pivot','consumed','publications','features'))
        rhs=g['rhs']
    pair={(j[1],j[2],j[3]):j[0] for j in compiled}
    leaf={(r,p):i for i,(r,p,_,_) in enumerate(entries) if r>=0}
    labels=defaultdict(lambda:defaultdict(set))
    for end in np.flatnonzero(ticket):
        child=leaf.get((int(rhs[end,1]),int(pivot[end])-1))
        parent,port,_,_=map(int,publications[ticket[end]-1]);i=parent-1
        root=leaf.get((int(rhs[i,1]),int(pivot[i])-1))
        unit=pair.get((root,port,child))
        if unit is None:continue
        run=int(rhs[i,0]);rank=np.flatnonzero(features[run-1,root*8:(root+1)*8,0]==rhs[i,3])
        if not len(rank):continue
        labels[(run,root*8+int(rank[0]),parent)][unit].add(end+1)
    return labels,features,rhs,publications,ticket


def decode_cache(native,entries):
    joins=native['joins'];j=len(joins);w=torch.tensor(native['child']);b=14*j
    cache=SimpleNamespace(joins=torch.tensor(joins),score=w[:b].reshape(j,14),
           row_score=w[b:b+2*j].reshape(2,j).clone(),embedding=w[b+2*j:b+10*j].reshape(j,8),
           null=w[b+10*j:b+10*j+2],row_latent=w[-16:].reshape(2,8))
    for i,(_,_,_,right) in enumerate(joins):
        if entries[right][0]<0:cache.row_score[:,i]=-1e6
    return cache


def conditioned(native,entries,root,labels,features,which):
    # A post-run diagnostic that supplies one known eligible root and a null peer,
    # at a zero previous latent for all arms. The actual online generator sees neither oracle.
    ids=[j[0] for j in native['joins']];allowed=set(ids);by_unit={j[0]:j for j in native['joins']}
    keys=[k for k,v in labels.items() if allowed.intersection(v)]
    keys.sort()
    result={}
    if not keys:return result
    runs=torch.tensor([k[0] for k in keys]);actions=torch.tensor([[k[1],-1] for k in keys])
    known=forced(root,torch.from_numpy(features[runs.numpy()-1]),torch.zeros(len(keys),2,12),actions)
    cache=decode_cache(native,entries)
    logits,_,chosen=CompoundActor.propose_children(cache,known,torch.zeros(len(keys),2,4),False,runs)
    # Reverse only the enumeration of joins within each possible parent; the same scalar
    # scores and the null/parent order are kept. Convert back to the original action IDs.
    j=len(ids)
    scores=logits[:,:,1:].reshape(len(keys),2,2,j).flip(-1).reshape(len(keys),2,-1)
    order=torch.cat([logits[:,:,:1],scores],-1).argmax(-1)
    ix=(order-1).clamp_min(0)
    reverse_choice=torch.where(order>0,1+(ix//j)*j+(j-1-ix%j),0).tolist()
    for group in ['all','seen','held_combination','held_left_family','growth']:
        contexts=covered=exact=tp=spurious=missing=flipped=reverse_tp=0
        competing_targets=competing_hits=0;null_miss=port_miss=consumer_miss=0
        for k,picks,rev in zip(keys,chosen.tolist(),reverse_choice):
            truth=allowed.intersection(labels[k]);guess={ids[(v-1)%len(ids)] for v in picks if v}
            all_guesses=guess
            alt={ids[(v-1)%len(ids)] for v in rev if v}
            if group!='all':
                alt={u for u in alt if which(u)==group}
                truth={u for u in truth if which(u)==group};guess={u for u in guess if which(u)==group}
            for lost in truth-guess:
                if not all_guesses:null_miss+=1
                elif any(by_unit[u][2]==by_unit[lost][2] for u in all_guesses):consumer_miss+=1
                else:port_miss+=1
            left=k[1]//8
            if sum(1 for _,l,_,right in native['joins'] if l==left and entries[right][0]>=0)>1:
                competing_targets+=len(truth);competing_hits+=len(guess&truth)
            flipped+=int(alt!=guess);reverse_tp+=len(alt&truth)
            contexts+=int(bool(truth));covered+=int(bool(truth) and truth<=guess);exact+=int(bool(truth) and truth==guess)
            tp+=len(truth&guess);spurious+=len(guess-truth);missing+=len(truth-guess)
        result[group]=dict(roots_with_positive=contexts,covered=covered,exact=exact,true_positive=tp,extra=spurious,missing=missing,
                           reversed_enumeration_changed_sets=flipped,reversed_enumeration_true_positive=reverse_tp,
                           targets_with_multiple_legal_joins=competing_targets,hits_with_multiple_legal_joins=competing_hits,
                           miss_all_abstain=null_miss,miss_different_effect=port_miss,miss_same_effect_wrong_receiver=consumer_miss)
    return result


def evaluate(folder,labels,ref_rhs,publications,consumed,entries,native,which):
    with np.load(folder/'output.npz') as g,np.load(folder/'neural-output.npz') as n,np.load(folder/'compound-output.npz') as q:
        rhs,tot=g['rhs'],g['runs'][:,1];roots=n['rhs_ordinal'][:,:2];raw=n['raw'];claims=q['claims'];status=n['verdict'][:,:2,0]
    joins=native['joins'];allowed={r[0] for r in joins}
    report={};root_ords=set(map(int,roots[roots>0]));child_ords=set()
    delivered=defaultdict(set);origins=defaultdict(set);issued=defaultdict(int);exact_tickets=0
    for t,lane in zip(*np.nonzero(claims[:,:,8])):
        par,j,o,row,ticket,release,bank,winner,state,*_=map(int,claims[t,lane])
        unit,left,port,right=joins[j];group=which(unit);issued[group]+=1
        assert int(raw[t,par,8])==left+1
        np.testing.assert_array_equal(raw[t,2+lane,8:],[right+1,2*t+par+1,port+1,1])
        if not winner:continue
        assert roots[t,par]==o and release>t+1 and rhs[winner-1,0]==release
        assert tuple(publications[ticket-1])==(o,port,row,entries[right][3])
        exact_tickets+=int(consumed[winner-1]==ticket)
        assert tuple(rhs[winner-1,[1,3]])==(entries[right][0],row)
        assert winner not in root_ords and winner not in child_ords
        child_ords.add(winner);delivered[group].add(winner);origins[group].add((o,unit,winner))
    for group in ['all','seen','held_combination','held_left_family','growth']:
        expected=set();expected_origins=set();issue_pairs=defaultdict(set)
        by_release=defaultdict(set)
        for (run,action,parent),units in labels.items():
            for unit,ends in units.items():
                if unit not in allowed or (group!='all' and which(unit)!=group):continue
                issue_pairs[run].add((action,unit))
                for o in ends:expected.add(o);expected_origins.add((parent,unit,o));by_release[int(ref_rhs[o-1,0])].add(o)
        wins=child_ords if group=='all' else delivered[group]
        source_origins=set().union(*origins.values()) if group=='all' else origins[group]
        report[group]=dict(emitted=sum(issued.values()) if group=='all' else issued[group],children=len(wins),
                           reference_child_rhs=len(expected),reference_reachable_pairs=sum(map(len,issue_pairs.values())),
                           two_slot_pair_bound=sum(min(2,len(g)) for g in issue_pairs.values()),
                           matched_reference=len(source_origins&expected_origins),alternative_origin=len(source_origins-expected_origins),
                           matching_semantic_ordinal=len(wins&expected),
                           release_runs=len(by_release),whole_release_runs=sum(target<=wins for target in by_release.values()))
    all_won=np.array(sorted(root_ords|child_ords),np.int64)
    hits=np.bincount(rhs[all_won-1,0].astype(np.int64),minlength=len(tot)+1)[1:]
    return dict(runs=len(tot),rhs=len(rhs),neural_roots=len(root_ords),neural_children=len(child_ords),
                exact=len(rhs)-len(all_won),same_source_child_tickets=exact_tickets,nonempty=int((tot>0).sum()),whole_nonempty=int(((tot>0)&(tot==hits)).sum()),
                parent_raw=int((status>0).sum()),parent_rejected=int((status==2).sum()),parent_duplicates=int((status==3).sum()),
                child_status=np.bincount(claims[:,:,8].flatten(),minlength=7).tolist(),cohorts=report,source_aligned=True)


def study(a):
    torch.set_num_threads(1);a.out.mkdir(parents=True,exist_ok=False)
    donor=a.ref/'sum-bits/program.json'
    joins,catalog,seen,cold,family=split(read(donor),a.train_size);results={}
    def which(unit):return cohort(unit,joins,catalog,seen,cold,family)
    for name in a.cases:
        image,p,gold=inputs(a.corpus,a.ref,name)
        entries=load_catalog(image,p,donor)
        labels,features,reference,pubs,consumed=opportunities(a.capture/name,entries,joins)
        with np.load(gold/'output.npz') as z:truth={k:z[k] for k in ('runs','writes','rhs','resumes')}
        for seed in a.seeds:
            root=Actor();root.load_state_dict(torch.load(a.root/f'train-{seed}/actor.pt',weights_only=True));root.eval()
            for size in a.sizes:
                sessions={};arms={};tokens={}
                for kind in ('id','graph','compose'):
                    folder=a.out/f'{name}-{seed}-{size}-{kind}'
                    model_dir=a.models/f'{kind}-{seed}-train{a.train_size}'
                    native=read(model_dir/f'cache-{size}.json')
                    assert native['joins']==[list(j) for j in joins if j[0]<size]
                    validate_join_ports(image,entries,native['joins'])
                    cfg=dict(catalog=entries,rows=2,hidden=8,ranks=8,waves=2,weights=native['roots'],
                             compound=dict(joins=native['joins'],child=native['child'],batch=True))
                    execute(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,folder,neural=cfg,
                            measure_resident=bind_session(sessions,kind))
                    verify(folder,gold,image)
                    arms[kind]=evaluate(folder,labels,reference,pubs,consumed,entries,native,which)
                    arms[kind]['conditioned']=conditioned(native,entries,root,labels,features,which)
                    arms[kind]['samples_ms']=[]
                    with np.load(folder/'neural-output.npz') as z:tokens[kind]=z['raw']
                    if size==max(a.sizes):
                        no=folder.with_name(folder.name+'-no-residual')
                        execute(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,no,
                                neural={**cfg,'complete_residual':False})
                        roles=read(no/'run.json')['execution_roles']
                        with np.load(no/'output.npz') as z:
                            actual=z['runs'];events=z['rhs'];source=truth['runs']
                            first=next((i+1 for i,(u,v) in enumerate(zip(actual,source)) if not np.array_equal(u,v)),None)
                            if first is None and len(actual)!=len(source):first=min(len(actual),len(source))+1
                            arms[kind]['autonomous']=dict(runs=len(actual),rhs=len(events),first_run_difference=first,
                                                         exact_rhs=roles['rhs_inputs_from_exact_search'])
                            assert first and roles['rhs_inputs_from_exact_search']==0
                if size==max(a.sizes):
                    base=a.out/f'{name}-{seed}-{size}-exact'
                    execute(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,base,
                            measure_resident=bind_session(sessions,'exact'))
                    verify(base,gold,image)
                    arms['exact']=dict(samples_ms=[],source_aligned=True)

                names=list(arms)
                for trial in range(2*len(names)):
                    order=names[trial%len(names):]+names[:trial%len(names)]
                    for kind in (order if trial<len(names) else order[::-1]):
                        reset,infer,buf=sessions[kind];reset();torch.mps.synchronize()
                        start=perf_counter_ns();infer();torch.mps.synchronize()
                        arms[kind]['samples_ms'].append((perf_counter_ns()-start)/1e6)
                        state=buf['state'].cpu().tolist();assert state[7] and not state[5]
                        for k,i in [('runs',11),('rhs',9),('writes',10),('resumes',16)]:
                            got,want=buf[k][:state[i]].cpu().numpy(),truth[k]
                            if k=='rhs':
                                np.testing.assert_array_equal(got[:,:2],want[:,:2]);got,want=got[:,4:],want[:,4:]
                            np.testing.assert_array_equal(got,want)
                        if kind!='exact':np.testing.assert_array_equal(buf['raw_trace'][:state[11]].cpu().numpy(),tokens[kind])
                for kind,r in arms.items():
                    r['median_ms']=median(r['samples_ms'])
                    if kind=='exact':continue
                    native=read(a.models/f'{kind}-{seed}-train{a.train_size}'/f'cache-{size}.json')
                    r['native_scorer']=measure_score(native,entries,tokens[kind])
                key=f'{name}/{seed}/{size}';results[key]=arms
                (a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
                print(key,[(k,r['neural_children'],r['cohorts']['held_left_family']['children'],
                            r['cohorts']['growth']['children'],round(r['median_ms'])) for k,r in arms.items() if k!='exact'],flush=True)
                sessions.clear()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','reader','capture','root','models','out'):p.add_argument(k,type=Path)
    p.add_argument('--train-size',type=int,default=40)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','gemm-bias-relu','stable-argmax'])
    p.add_argument('--sizes',type=int,nargs='+',default=[40,48,64])
    p.add_argument('--seeds',type=int,nargs='+',default=[1703,1709])
    with torch.inference_mode():study(p.parse_args())

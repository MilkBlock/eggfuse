"""Offline full-stream proof retirement on real learned parent edges and recorded source-anchor dependencies."""
import argparse
from collections import defaultdict,deque
import json
from pathlib import Path
from statistics import median
import sys
from time import perf_counter_ns

import numpy as np
import torch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'recurrent-generator'))
from capture import inputs,load_catalog,read


def graph(a,n,seed):
    image,program,_=inputs(a.corpus,a.ref,n);entries=load_catalog(image,program,a.ref/'sum-bits/program.json')
    tables=read(image/'ingress.json')['tables'];folder=a.paired/f'{n}-{seed}-batch'
    with np.load(folder/'neural-output.npz') as z,np.load(folder/'compound-output.npz') as c,np.load(folder/'output.npz') as g:
        root=z['rhs_ordinal'][:,:2];raw=z['raw'];claims=c['claims'];rhs=g['rhs']
    with np.load(a.capture/n/'neural-inputs.npz') as z,np.load(a.capture/n/'output.npz') as g:
        publications=z['publications'];consumed=z['consumed'];pivot=z['pivot'];reference=g['rhs']
    issue={};explicit_parent={};leaf={};anchor={}
    for t,lane in zip(*np.nonzero(root)):
        o=int(root[t,lane]);issue[o]=t+1;leaf[o]=int(raw[t,lane,8])-1;anchor[o]=int(raw[t,lane,9])-1
    for t,lane in zip(*np.nonzero(claims[:,:,7])):
        parent,j,origin,row,ticket,boundary,_,o,*_=map(int,claims[t,lane])
        assert origin==root[t,parent] and int(publications[ticket-1,0])==origin
        issue[o]=t+1;explicit_parent[o]=origin;leaf[o]=int(raw[t,lane+2,8])-1;anchor[o]=row
    ordinals=sorted(issue);index={o:i for i,o in enumerate(ordinals)}
    data=[];implicit=forwarded=0;depth=[]
    for o in ordinals:
        rid,p,_,table=entries[leaf[o]]
        assert tuple(rhs[o-1,[1,3]])==(rid,anchor[o])
        parent=explicit_parent.get(o)
        if parent is None and consumed[o-1] and pivot[o-1]==p+1 and reference[o-1,3]==anchor[o]:
            source,_,row,tab=map(int,publications[consumed[o-1]-1])
            if source in index:
                assert tab==table
                parent=source;implicit+=1
                # The capture stores the publication ticket visible at the observed physical anchor.
                # Rebuild may have forwarded that ticket from a different physical source row.
                forwarded+=int(row!=anchor[o])
        before=index[parent] if parent is not None else -1
        assert before<index[o]
        depth.append(1 if before<0 else depth[before]+1)
        data.append([int(issue[o]),int(rhs[o-1,0]),before,o])
    facts=defaultdict(set)
    for source,effect,row,tab in publications:
        if source in index and tables[tab]['kind']=='constructor':
            # Fact presence is a separate claim from who published a specific input ticket.
            # Several effects by the same RHS provide only one independent source certificate.
            facts[(int(rhs[source-1,0]),int(tab),int(row))].add(index[int(source)])
    groups=[sorted(v) for v in facts.values()]
    return (np.asarray(data,np.int32),[index[int(o)] for o in root[root>0]],groups,list(facts),
            dict(proofs=len(data),learned_parent_edges=len(explicit_parent),source_anchor_edges=implicit,source_edges_after_anchor_forwarding=forwarded,
                 depth_with_source_edges=max(depth),constructor_facts=len(groups),known_multi_support=sum(len(g)>1 for g in groups)))


def oracle(proofs,roots,groups,coarse):
    # Queue the earliest invalidation boundary of each proof. Previously published proofs are protected.
    n=len(proofs);siblings=defaultdict(list);children=defaultdict(list);expected=[];summary=[]
    for idx,(issue,release,parent,_) in enumerate(proofs):
        siblings[issue].append(idx)
        if parent>=0:children[parent].append(idx)
    for root in roots:
        lost=[0]*n;work=deque([(root,int(proofs[root,0]))])
        while work:
            idx,when=work.popleft()
            if when>proofs[idx,1] or (lost[idx] and lost[idx]<=when):continue
            lost[idx]=when
            for child in children[idx]:work.append((child,max(when,int(proofs[child,0]))))
            if coarse:
                for sib in siblings[proofs[idx,0]]:work.append((sib,when))
        absent=affected=survive=scan=0
        for group in groups:
            slots=[bool(lost[i]) for i in group]
            if not any(slots):continue
            affected+=1
            if all(slots):absent+=1;scan+=len(slots)
            else:survive+=1;scan+=slots.index(False)+1
        expected.append(lost);summary.append((absent,affected,survive,scan))
    return np.asarray(expected,np.int32),np.asarray(summary,np.int32)


def study(a):
    if not torch.backends.mps.is_available():raise ValueError('requires MPS')
    lib=torch.mps.compile_shader((HERE/'support.metal').read_text())
    a.out.mkdir(parents=True,exist_ok=False)
    reports={}
    for case in a.cases:
        for seed in a.seeds:
            proof,roots,groups,keys,shape=graph(a,case,seed);n=len(proof)
            if a.visibility:
                states={tuple(row[:3]):row[3] for row in read(a.visibility)[case]}
                shape['published_constructor_records']=len(groups)
                shape['published_multi_support']=shape['known_multi_support']
                live=[(group,key) for group,key in zip(groups,keys) if states[key]==0]
                groups=[group for group,_ in live];keys=[key for _,key in live]
                shape['constructor_facts']=len(groups)
                shape['known_multi_support']=sum(len(group)>1 for group in groups)
                shape['checked_post_rebuild_visibility']=True
            ancestors=[]
            for index,(_,_,parent,_) in enumerate(proof):
                ancestors.append({index}|(ancestors[parent] if parent>=0 else set()))
            diamond=independent=0
            for group in groups:
                pairs=[(x,y) for i,x in enumerate(group) for y in group[i+1:]]
                diamond+=int(any(ancestors[x]&ancestors[y] and x not in ancestors[y] and y not in ancestors[x]
                                 for x,y in pairs))
                independent+=int(any(ancestors[x].isdisjoint(ancestors[y]) for x,y in pairs))
            shape.update(shared_ancestor_diamonds=diamond,disjoint_support_groups=independent)
            produces=[[] for _ in proof]
            for f,group in enumerate(groups):
                for i in group:produces[i].append(f)
            inputs=[proof,roots,np.cumsum([0,*map(len,groups)]),[i for g in groups for i in g],
                    np.cumsum([0,*map(len,produces)]),[f for fs in produces for f in fs]]
            packet=[torch.as_tensor(x,device='mps',dtype=torch.int32) for x in inputs]
            counter={};work={};examples=[];timing=[[],[],[]]
            for idx,name in enumerate(['batch','dependencies','supports']):
                out=torch.zeros((len(roots),n),device='mps',dtype=torch.int32)
                metrics=torch.zeros((len(roots),6),device='mps',dtype=torch.int32)
                scratch=torch.zeros((len(roots),len(groups)),device='mps',dtype=torch.int32)
                args=(*packet,out,scratch,metrics,n,len(groups),idx)
                lib.withdraw(*args,threads=len(roots),arg_casts={9:'int32',10:'int32',11:'int32'})
                loss=out.cpu().numpy();actual=metrics.cpu().numpy()
                expected,counts=oracle(proof,roots,groups,idx==0)
                np.testing.assert_array_equal(loss,expected)
                np.testing.assert_array_equal(actual[:,0],(loss>0).sum(1))
                np.testing.assert_array_equal(actual[:,2],counts[:,0])
                if idx==2:
                    np.testing.assert_array_equal(actual[:,4],counts[:,2]);assert not actual[:,3].any() and not actual[:,5].any()
                    # Recover a real multi-support constructor where the surviving support is independent.
                    for h in range(len(roots)):
                        for key,group in zip(keys,groups):
                            alive=[i for i in group if not loss[h,i]];removed=[i for i in group if loss[h,i]]
                            if alive and removed:
                                examples.append(dict(withdrawn_root=int(proof[roots[h],3]),source_run=key[0],table=key[1],
                                    physical_row=key[2],lost_rhs=list(map(int,proof[removed,3])),
                                    surviving_rhs=list(map(int,proof[alive,3]))))
                                break
                        if examples:break
                else:
                    np.testing.assert_array_equal(actual[:,3],counts[:,1]);np.testing.assert_array_equal(actual[:,5],counts[:,3])
                work[name]=dict(zip(['retired_proofs','surviving_proofs','unsupported_constructor_facts','dirty_memberships',
                                     'immediately_retained_alternatives','source_rechecks'],map(int,actual.sum(0))))
                counter[name]=(args,out,scratch,metrics)
            arms=list(counter)
            for repeat in range(12):
                for name in arms[repeat%3:]+arms[:repeat%3]:
                    args,out,scratch,metrics=counter[name];torch.mps.synchronize()
                    start=perf_counter_ns();out.zero_();scratch.zero_();metrics.zero_();lib.withdraw(*args,threads=len(roots),arg_casts={9:'int32',10:'int32',11:'int32'})
                    torch.mps.synchronize();timing[arms.index(name)].append((perf_counter_ns()-start)/1e6)
            for idx,name in enumerate(arms):
                work[name]['full_stream_counterfactual_group_ms']=timing[idx];work[name]['median_ms']=median(timing[idx])
            assert work['dependencies']['retired_proofs']==work['supports']['retired_proofs']
            assert work['dependencies']['unsupported_constructor_facts']==work['supports']['unsupported_constructor_facts']
            reports[f'{case}/{seed}']=dict(exhaustive_single_root_withdrawals=len(roots),shape=shape,policies=work,examples=examples,
                                           mps=True,independent_oracle=True)
            (a.out/'results.json').write_text(json.dumps(reports,indent=1)+'\n')
            print(case,seed,shape['depth_with_source_edges'],shape['known_multi_support'],work['supports']['immediately_retained_alternatives'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('corpus','ref','capture','paired','out'):p.add_argument(name,type=Path)
    p.add_argument('--visibility',type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','gemm-bias-relu','stable-argmax'])
    p.add_argument('--seeds',type=int,nargs='+',default=[1703,1709])
    with torch.inference_mode():study(p.parse_args())

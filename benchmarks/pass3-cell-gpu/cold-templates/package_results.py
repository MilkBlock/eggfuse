"""Keep per-Run root reach separate from scoring while packaging the online measurements."""
import argparse
import json
import hashlib
from collections import defaultdict
from pathlib import Path
import numpy as np
import torch
from study import cohort,opportunities,conditioned,Actor
from policy import split,read
from capture import inputs,load_catalog


@torch.inference_mode()
def package(a):
    torch.set_num_threads(1)
    a.out.mkdir(exist_ok=True,parents=True)
    records=read(a.paired/'results.json');train={}
    for p in sorted(a.models.glob('*-train40/training.json')):
        d=read(p)
        for size,snapshot in d['snapshots'].items():
            manifest=p.parent/f'cache-{size}.json';native=read(manifest)
            j=len(native['joins']);coef=np.asarray(native['child'],np.float32)
            matrix=np.concatenate((coef[:14*j].reshape(j,14),coef[14*j:16*j].reshape(2,j).T,
                                   coef[16*j:24*j].reshape(j,8)),axis=1)
            unseen=[i for i,row in enumerate(native['joins']) if row[0] not in d['seen']]
            snapshot['cold_units']=len(unseen)
            snapshot['distinct_cold_codes']=len(np.unique(matrix[unseen],axis=0))
            snapshot['native_sha256']=hashlib.sha256(manifest.read_bytes()).hexdigest()
            if d['kind']=='id':assert snapshot['distinct_cold_codes']==1
        train[f"{d['kind']}/{d['seed']}"]=d
    assert len(records)==24 and len(train)==6
    donor=a.ref/'sum-bits/program.json';joins,catalog,seen,cold,family=split(read(donor))
    cases={}
    for key,arms in records.items():
        name,seed,size=key.split('/');size=int(size)
        if name not in cases:
            image,p,_=inputs(a.corpus,a.ref,name)
            entries=load_catalog(image,p,donor)
            labels,features,*_=opportunities(a.capture/name,entries,joins)
            cases[name]=labels,features,entries
        labels,features,entries=cases[name]
        for kind,v in arms.items():
            if kind=='exact':continue
            saved=a.paired/f'{name}-{seed}-{size}-{kind}'
            with np.load(saved/'neural-output.npz') as z,np.load(saved/'compound-output.npz') as c:
                order=z['rhs_ordinal'][:,:2];raw=z['raw'][:,:2];claims=c['claims']
            native=read(a.models/f'{kind}-{seed}-train40'/f'cache-{size}.json')
            root=Actor();root.load_state_dict(torch.load(a.root/f'train-{seed}/actor.pt',weights_only=True));root.eval()
            enriched=conditioned(native,entries,root,labels,features,lambda u:cohort(u,joins,catalog,seen,cold,family))
            for g,stats in v['conditioned'].items():
                for metric,value in stats.items():assert enriched[g][metric]==value
            v['conditioned']=enriched
            eligible=defaultdict(int)
            for _,left,_,right in native['joins']:
                if entries[right][0]>=0:eligible[left]+=1
            competing=defaultdict(int);examples=defaultdict(list)
            for issue,row in zip(*np.nonzero(claims[:,:,7])):
                parent,jid,origin,physical,ticket,release,_,winner,*_=map(int,claims[issue,row])
                unit,left,port,right=native['joins'][jid];cg=cohort(unit,joins,catalog,seen,cold,family)
                if eligible[left]>1:competing[cg]+=1
                if len(examples[cg])<3:examples[cg].append(dict(issue=int(issue+1),release=release,unit=unit,
                    parent_rule=entries[left][0],port=port,consumer_rule=entries[right][0],parent_rhs=origin,
                    row=physical,ticket=ticket,child_rhs=winner,legal_joins_for_parent=eligible[left]))
            v['examples']=dict(examples)
            rootset=set()
            for t,lane in zip(*np.nonzero(order)):
                token=raw[t,lane];action=(int(token[8])-1)*8+int(token[10])-1
                assert int(token[9])-1==features[t,action,0]
                rootset.add((int(t+1),action,int(order[t,lane])))
            for group,stats in v['cohorts'].items():
                possibilities=defaultdict(set);ends=set();sites=0
                for k in rootset:
                    if k not in labels:continue
                    here=0
                    for unit,out in labels[k].items():
                        if unit>=size or (group!='all' and cohort(unit,joins,catalog,seen,cold,family)!=group):continue
                        possibilities[k[0]].add((k[2],unit))
                        ends.update(out);here+=1
                    sites+=int(here>0)
                stats['wins_with_multiple_legal_joins']=sum(competing.values()) if group=='all' else competing[group]
                stats['winning_roots_with_opportunity']=sites
                stats['reference_rhs_behind_actual_roots']=len(ends)
                stats['two_slot_bound_given_actual_roots']=sum(min(2,len(v)) for v in possibilities.values())
                assert stats['matched_reference']<=stats['two_slot_bound_given_actual_roots']<=stats['two_slot_pair_bound']
    (a.out/'training.json').write_text(json.dumps(train,indent=1)+'\n')
    (a.out/'results.json').write_text(json.dumps(records,indent=1)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','capture','root','models','paired','out'):p.add_argument(k,type=Path)
    package(p.parse_args())

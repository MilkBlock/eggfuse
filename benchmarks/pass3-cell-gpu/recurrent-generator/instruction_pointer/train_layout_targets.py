"""Train one direct graph action head on all observed alternatives at a decision."""
import argparse
import gzip
import json
from pathlib import Path

import torch
from torch.nn import functional as F

from alternate_proofs import digest
from higher_cell import read
from ripsat_replay import unpack
from train_layout_bandit import Utility,fixed_features
from train_ripsat import layout_id


def load_data(folder,baked,mode):
    manifests=read(baked/'study.json')['training_traces']
    held={i for i,g in enumerate(unpack(read(baked/'catalog.json'))) if int(layout_id(g)[:8],16)%8==0}
    menus={}
    rows=[]
    provenance={}
    for name,trace in manifests.items():
        meta=read(folder/(name+'.json'))
        path=folder/(name+'.json.gz')
        if (meta['data']!=digest(path) or meta['catalog']!=digest(baked/'catalog.json') or
            meta['trace']!=trace or meta['program']!=name):
            raise ValueError('stale or incorrect supervision')
        with gzip.open(path,'rt') as f:
            data=json.load(f)
        indices=[]
        positions=[]
        for opts in data['menus']:
            if held.intersection(opts):
                raise ValueError('held layout in action menu')
            indices.append(menus.setdefault(tuple(opts),len(menus)))
            positions.append({u:j+1 for j,u in enumerate(opts)})
        for k,x,targets in data['rows']:
            values=[(positions[k][u],r if mode=='observed' else b) for u,r,b in targets]
            rows.append((indices[k],x,[(j,v) for j,v in values if v>0]))
        provenance[name]=meta
    width=max(map(len,menus))+1
    ids=torch.zeros(len(menus),width,dtype=torch.long)
    mask=torch.zeros_like(ids,dtype=torch.bool)
    for opts,k in menus.items():
        ids[k,1:len(opts)+1]=torch.tensor(opts)+1
        mask[k,:len(opts)+1]=True
    labels=torch.zeros(len(rows),width)
    for i,(_,_,ys) in enumerate(rows):
        if ys:
            j,v=zip(*ys)
            labels[i,list(j)]=torch.tensor(v,dtype=torch.float)
        else:
            labels[i,0]=1
    labels/=labels.sum(dim=1,keepdim=True)
    return (torch.tensor([k for k,_,_ in rows]),torch.tensor([x for _,x,_ in rows]),
            labels,ids,mask),provenance


def fit(data,baked,out,mode,epochs,static=False):
    (menu,x,labels,ids,mask),provenance=load_data(data,baked,mode)
    if static:
        x.zero_()
    positives=torch.where(labels[:,0]==0)[0]
    negatives=torch.where(labels[:,0]>0)[0]
    if min(len(positives),len(negatives))==0:
        raise ValueError('training requires both positive and standalone decisions')
    device='mps'
    graph,_=fixed_features(baked)
    graph=graph.to(device)
    torch.manual_seed(1703)
    model=Utility(x.shape[1],graph.shape[1]).to(device)
    opt=torch.optim.AdamW(model.parameters(),lr=.004)
    menu,x,labels,ids,mask=[t.to(device) for t in (menu,x,labels,ids,mask)]
    # Cover each positive decision every epoch. Balance standalone decisions so
    # sparse observed opportunities still contribute to the graph comparisons.
    for _ in range(epochs):
        pos=positives[torch.randperm(len(positives))]
        neg=negatives[torch.randint(len(negatives),(len(pos),))]
        for a,b in zip(pos.split(96),neg.split(96),strict=True):
            idx=torch.cat((a,b)).to(device)
            m=menu[idx]
            scores=model(x[idx],graph).gather(1,ids[m]).masked_fill(~mask[m],-1e6)
            loss=-(F.log_softmax(scores,dim=1)*labels[idx]).sum(1).mean()
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(),2.)
            opt.step()
    out.mkdir(exist_ok=True,parents=True)
    torch.save(model.cpu().state_dict(),out/'policy.pt')
    result=dict(objective='within_root_set',labels=mode,epochs=epochs,device=device,
                positive=len(positives),standalone=len(negatives),data=provenance,
                policy=digest(out/'policy.pt'),bake={k:digest(baked/k) for k in
                ('codes.pt','catalog.json','shared.pt','boundary.pt')})
    if static:
        # The selector receives no instance fields in this ablation. Its logits
        # are constants for a frozen catalog, including layouts held from training.
        with torch.no_grad():
            scores=model(torch.zeros(1,x.shape[1]),graph.cpu())[0]
        torch.save(scores,out/'scores.pt')
        result['static_scores']=digest(out/'scores.pt')
    (out/'training.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('data','baked','out'):
        p.add_argument(key,type=Path)
    p.add_argument('--labels',choices=['observed','readable'],required=True)
    p.add_argument('--static',action='store_true')
    p.add_argument('--epochs',type=int,default=48)
    a=p.parse_args()
    torch.set_num_threads(1)
    fit(a.data,a.baked,a.out,a.labels,a.epochs,a.static)

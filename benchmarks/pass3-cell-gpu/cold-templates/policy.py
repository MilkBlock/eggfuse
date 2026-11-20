"""Train only the template head; compile its output to the same device scoring ABI for all arms."""
import argparse
import json
from pathlib import Path
from statistics import median
import sys
from time import perf_counter_ns
from types import SimpleNamespace

import numpy as np
import torch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'recurrent-generator'))
from compound_model import CompoundActor,pair_joins
from feedback import training_reply
from model import Actor,ROWS,HIDDEN,RANKS,set_loss
from graph import Catalog,TemplateHead


def read(path):return json.loads(path.read_text())


def split(program,train_size=40):
    joins=pair_joins(program);catalog=Catalog(program,joins)
    first=[i for i,j in enumerate(joins) if j[0]<40]
    families=list(dict.fromkeys(catalog.family[i] for i in first))
    held_family=families[1]
    allowed=[i for i in first if catalog.family[i]!=held_family]
    # Choose the earliest combination and a self-composition with known component leaves.
    held_units={joins[allowed[0]][0],next(joins[i][0] for i in allowed if joins[i][1]==joins[i][3])}
    seen=[i for i,j in enumerate(joins) if j[0]<train_size and j[0] not in held_units and catalog.family[i]!=held_family]
    return joins,catalog,seen,held_units,held_family


def tensors(head,catalog,indices,pack):
    joins=[catalog.joins[i] for i in indices]
    values=head([j[0] for j in joins],pack)
    return SimpleNamespace(joins=torch.tensor(joins),score=values[:,:14],row_score=values[:,14:16].T,
                           embedding=values[:,16:],null=head.null,row_latent=head.row_latent)


def export(cache):
    return torch.cat([t.detach().contiguous().flatten() for t in
                      (cache.score,cache.row_score,cache.embedding,cache.null,cache.row_latent)]).tolist()


def forced(root,obs,previous,address):
    """Auxiliary training/diagnostic only. Apply the frozen root readout to a specified physical candidate."""
    stage=obs[:,0,1].long()%32
    prior=previous[:,:,HIDDEN+1:]/previous.new_tensor([16384.,8.,1.])
    state=(previous[:,:,:HIDDEN]@root.recurrent.T+prior@root.previous.T+
           root.templates[previous[:,:,HIDDEN].long()]+root.stages[stage,None,:]+root.rows).tanh()
    active=address>=0;idx=address.clamp_min(0)
    feature=obs.gather(1,idx[:,:,None].expand(-1,-1,obs.shape[-1]))
    local=feature[:,:,2:].float()/root.scale
    key=(root.templates[idx//RANKS+1]+root.positions[idx%RANKS]+local@root.read.T).tanh()
    fields=torch.stack([idx//RANKS+1,feature[:,:,0]+1,idx%RANKS+1,active],-1)*active[:,:,None]
    return torch.cat([(state+active[:,:,None]*key).tanh(),fields.float()],-1)


def desired(roots,labels,outcomes):
    action=((roots[...,HIDDEN].long()-1)*RANKS+roots[...,HIDDEN+2].long()-1).clamp_min(0)
    verdict,_=training_reply(roots.detach(),outcomes,torch.zeros_like(outcomes,dtype=torch.bool))
    selected=labels.gather(1,action[...,None].expand(-1,-1,labels.shape[-1])) & (verdict[...,0:1]==1)
    return selected.reshape(len(roots),-1),verdict


def train(a,seed,kind):
    torch.manual_seed(seed);torch.set_num_threads(1)
    rng=np.random.default_rng(seed)
    program=read(a.donor)
    joins,catalog,seen,cold,family=split(program,a.train_size)
    selected=[joins[i][0] for i in seen];lookup={unit:j for j,unit in enumerate(selected)}
    head=TemplateHead(kind,catalog,selected)
    root=Actor();root.load_state_dict(torch.load(a.root/f'train-{seed}/actor.pt',weights_only=True))
    root.requires_grad_(False).eval()
    names=sorted(p.stem for p in (a.targets/'train').glob('*.npz'))
    assert names==sorted(read(a.root/f'train-{seed}/actor.json')['train'])
    ds=[]
    for n in names:
        with np.load(a.observations/n/'training.npz') as z:
            x=torch.from_numpy(z['features']);r=torch.from_numpy(z['receipt'])
        y=torch.zeros(len(x),x.shape[1],len(selected),dtype=torch.bool)
        with np.load(a.targets/'train'/f'{n}.npz') as z:
            for run,leaf,rank,unit,depth,*_ in z['targets']:
                if depth==2 and int(unit) in lookup:y[run-1,leaf*RANKS+rank,lookup[unit]]=True
        ds.append((x,r,y,np.flatnonzero(y.any((1,2)).numpy())))
    view=catalog.subset(seen,kind)
    opt=torch.optim.Adam(head.parameters(),lr=.005)
    losses=[]
    for update in range(a.updates):
        batch=[]
        for j in range(12):
            x,r,y,event=ds[int(rng.integers(len(ds)))]
            end=int(rng.choice(event)) if j%3 and len(event) else int(rng.integers(7,len(x)))
            start=max(0,end-7)
            batch.append((x[start:start+8],r[start:start+8],y[start:start+8],torch.arange(start+1,start+9)))
        x,r,y,run=map(torch.stack,zip(*batch))
        cache=tensors(head,catalog,seen,view)
        prev=torch.zeros(len(x),ROWS,HIDDEN+4); loss=0
        for tick in range(x.shape[1]):
            obs,labels,outcomes=x[:,tick],y[:,tick],r[:,tick]
            _,parents=root.step(obs,prev)
            target,reply=desired(parents,labels,outcomes)
            score,next_token,_=CompoundActor.propose_children(cache,parents,reply,False,run[:,tick])
            loss=loss+set_loss(score,target)
            # Supply up to two distinct *training* roots in a separate auxiliary head readout.
            # The actual recurrence always receives its own generated token.
            valid=labels.any(-1)
            noise=torch.from_numpy(rng.random(size=valid.shape).astype(np.float32))
            rank=noise.masked_fill(~valid,-1).topk(2).indices
            forced_addr=torch.where(valid.gather(1,rank),rank,-1)
            parents_aux=forced(root,obs,prev,forced_addr)
            target,reply=desired(parents_aux,labels,outcomes)
            score,_,_=CompoundActor.propose_children(cache,parents_aux,reply,False,run[:,tick])
            loss=loss+set_loss(score,target)
            prev=next_token
        loss=loss/(2*x.shape[1]);opt.zero_grad();loss.backward()
        torch.nn.utils.clip_grad_norm_(head.parameters(),1.);opt.step()
        if update%40==0:losses.append(float(loss.detach()))
    folder=a.out/f'{kind}-{seed}-train{a.train_size}';folder.mkdir(parents=True,exist_ok=False)
    torch.save(head.state_dict(),folder/'head.pt')
    summary=dict(seed=seed,kind=kind,width=12,train_size=a.train_size,seen=selected,cold=sorted(cold),held_family=family,
                 families=names,updates=a.updates,window=8,batch=12,trainable_parameters=sum(p.numel() for p in head.parameters()),
                 root_parameters=sum(p.numel() for p in root.parameters()),loss=losses,snapshots={})
    with torch.inference_mode():
        bank=None;prior=[];prior_cache=None
        begin=perf_counter_ns()
        if kind=='compose':bank=head.leaf_bank(catalog)
        summary['leaf_cache_build_ms']=(perf_counter_ns()-begin)/1e6 if bank is not None else 0.
        summary['leaf_cache_bytes']=sum(v.numel()*v.element_size() for row in bank for v in row) if bank is not None else 0
        for size in (40,48,64):
            ids=[i for i,j in enumerate(joins) if j[0]<size]
            samples=[];cold_time=[]
            for repeat in range(25):
                start=perf_counter_ns();packet=catalog.subset(ids,kind)
                cache=tensors(head,catalog,ids,packet);elapsed=perf_counter_ns()
                cold_time.append((elapsed-start)/1e6)
                start=perf_counter_ns();tensors(head,catalog,ids,packet);samples.append((perf_counter_ns()-start)/1e6)
            new=ids[len(prior):];grow=[]
            for repeat in range(25):
                start=perf_counter_ns();added=head.compile_new(catalog,new,bank)
                combined=torch.cat([prior_cache,added]) if prior_cache is not None else added
                grow.append((perf_counter_ns()-start)/1e6)
            fresh=head([joins[i][0] for i in ids],catalog.subset(ids,kind))
            err=float((combined-fresh).abs().max())
            assert err<1e-5, (kind,size,err)
            cache=SimpleNamespace(joins=cache.joins,score=combined[:,:14],row_score=combined[:,14:16].T,
                                  embedding=combined[:,16:],null=head.null,row_latent=head.row_latent)
            prior=ids;prior_cache=combined
            coef=export(cache)
            compiled=dict(schema='eggfuse.compound-pair/v1',joins=cache.joins.tolist(),roots=root.metal_weights(),child=coef)
            (folder/f'cache-{size}.json').write_text(json.dumps(compiled,separators=(',',':'))+'\n')
            summary['snapshots'][size]=dict(units=size,admitted_pairs=len(ids),template_bytes=len(ids)*24*4,
                new_pairs=len(new),incremental_first_ms=grow[0],incremental_median_ms=median(grow),
                full_vs_incremental_cache_error=err,common_bias_bytes=18*4,encoded_bytes=len(coef)*4,first_graph_build_and_encode_ms=cold_time[0],
                median_graph_build_and_encode_ms=median(cold_time),cached_graph_encode_ms=median(samples))
    (folder/'training.json').write_text(json.dumps(summary,indent=1)+'\n')
    print(seed,kind,summary['seen'],summary['loss'][-1],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('donor','root','observations','targets','out'):p.add_argument(k,type=Path)
    p.add_argument('--seeds',type=int,nargs='+',default=[1703,1709])
    p.add_argument('--arms',nargs='+',default=['id','graph','compose'])
    p.add_argument('--updates',type=int,default=480)
    p.add_argument('--train-size',type=int,default=40)
    a=p.parse_args()
    for seed in a.seeds:
        for arm in a.arms:train(a,seed,arm)

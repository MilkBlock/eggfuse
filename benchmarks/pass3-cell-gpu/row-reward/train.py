"""Fine-tune a shared 2x4 recurrent policy on family-isolated native candidate windows."""
import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import numpy as np
import torch
from torch import nn

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('unit_policy',HERE.parent/'action-granularity/model.py')
unit=importlib.util.module_from_spec(spec);spec.loader.exec_module(unit)
ROWS,RANKS,H=2,8,8


def decision(net,x,prev,allowed,child,sample):
    root=net.root;b=len(x)
    state=(prev[:,:,:H]@root.recurrent.T+(prev[:,:,9:]/prev.new_tensor([16384.,8.,1.]))@root.previous.T+
           root.templates[prev[:,:,8].long()]+root.stages[x[:,0,1].long()%32,None]+root.rows).tanh()
    local=x[:,:,2:].float()/root.scale
    keys=((root.templates[1:,None]+root.positions).reshape(1,256,8)+local@root.read.T).tanh()
    scores=state@keys.transpose(1,2)+root.bias.repeat_interleave(8)+(local@root.local_score)[:,None]
    scores=scores.masked_fill(~allowed,-1e4)
    logits=torch.cat([(state@root.abstain[:8]+root.abstain[8])[:,:,None],scores],2)
    prob=logits.softmax(-1)
    choice=torch.multinomial(prob.reshape(-1,257),1).reshape(b,2) if sample else logits.argmax(-1)
    active=choice>0;idx=(choice-1).clamp_min(0)
    selected=keys.gather(1,idx[:,:,None].expand(-1,-1,8))*active[:,:,None]
    soft=prob[:,:,1:]@keys
    latent=(state+selected+(soft-soft.detach())).tanh()
    leaf=idx//8;rank=idx%8;addr=x[:,:,0].gather(1,idx)
    code=latent@net.unit_weights.T+net.unit_bias+net.unit_row
    code=code.masked_fill(~active[:,:,None] | (leaf[:,:,None]!=net.joins[:,1]),-1e4)
    code_logits=torch.cat([net.stop[None,:,None].expand(b,-1,-1),code],-1)
    cp=code_logits.softmax(-1)
    chosen=torch.multinomial(cp.reshape(-1,cp.shape[-1]),1).reshape(b,2) if sample else code_logits.argmax(-1)
    join=(chosen-1).clamp_min(0)
    next_latent=(latent+net.unit_embed[join]*(chosen>0)[:,:,None]).tanh()
    fields=torch.stack([(leaf+1)*active,(addr+1)*active,(rank+1)*active,active],-1)
    child_labels=child.gather(1,idx[:,:,None].expand(-1,-1,child.shape[-1]))
    eligible=(child_labels>0)&active[:,:,None]
    outcome=child_labels.gather(-1,join[:,:,None]).squeeze(-1)*(chosen>0)
    logp=logits.log_softmax(-1).gather(-1,choice[:,:,None]).squeeze(-1)+code_logits.log_softmax(-1).gather(-1,chosen[:,:,None]).squeeze(-1)
    correct_code=torch.cat([~eligible.any(-1,keepdim=True),eligible],-1)
    code_loss=-(cp*correct_code).sum(-1).clamp_min(1e-10).log()
    code_loss=(code_loss*torch.where(eligible.any(-1),1.,.06)).mean()
    return prob,idx,active,outcome,logp,code_loss,torch.cat([next_latent,fields],-1)


def cost_fit(calibration):
    weights=np.asarray(calibration['net_us'])
    # Duplicate timings are confounded with small, cheap rules. Do not pay for
    # duplicates (ownership already excludes them); charge attempts and recurring overhead.
    return weights


def train(a,seed):
    torch.set_num_threads(1);torch.manual_seed(seed)
    joins=unit.joins_for(unit.read(a.donor));net=unit.Actor(joins)
    pretrained=a.weights/f'train-{seed}'
    net.load_state_dict(torch.load(pretrained/'actor.pt',map_location='cpu',weights_only=True))
    source_weights=unit.read(pretrained/'model.json')
    calibration=unit.read(a.native/'calibration.json')
    data=[]
    for name in sorted(calibration['programs']):
        with np.load(a.native/f'{name}.npz') as z:
            x,y,children=[torch.from_numpy(z[key]) for key in ('features','labels','children')]
            data.append((x,y,children,np.flatnonzero(y.any(1))))
    params=cost_fit(calibration)
    rule_meta=unit.read(a.donor)['recipe']['rules']
    entries=unit.read(a.donor)['spine_blocks']['entries']
    size=torch.tensor([len(rule_meta[e['consumer']]['query']) for e in entries])
    def updates(model,arm,num,offset):
        rng=np.random.default_rng(seed+offset);torch.manual_seed(seed+offset)
        opt=torch.optim.Adam(model.parameters(),lr=.002)
        logs=[];moving=0.
        for step in range(num):
            batch=[]
            for j in range(8):
                x,y,c,positives=data[rng.integers(len(data))]
                end=int(rng.choice(positives)) if j%2==0 else int(rng.integers(3,len(x)))
                start=max(0,end-3);batch.append((x[start:start+4],y[start:start+4],c[start:start+4]))
            features,y,children=map(torch.stack,zip(*batch));prev=torch.zeros(len(batch),2,12)
            losses=[];policy_loss=[];rewards=[];seen=[set() for _ in batch]
            for tick in range(4):
                x=features[:,tick];addr=x[:,:,0];leaf=torch.arange(256)//8
                present=addr>=0
                owner=(addr.long()*0x9e3779b1+leaf*0x85ebca77)%2
                reserved=torch.zeros_like(present)
                for _ in range(4):
                    allowed=present[:,None]&~reserved[:,None]&(owner[:,None]==torch.arange(2)[None,:,None])
                    target=allowed&y[:,tick,None]
                    prob,idx,active,outcome,logp,aux,prev=decision(model,x,prev,allowed,children[:,tick],True)
                    target_mass=(prob[:,:,1:]*target).sum(-1)
                    supervised=-torch.where(target.any(-1),target_mass,prob[:,:,0]).clamp_min(1e-10).log()
                    losses.append((supervised*torch.where(target.any(-1),1.,.15)).mean()+aux)
                    win=active&y[:,tick].gather(1,idx)
                    release=np.zeros((len(batch),2),dtype=np.float32)
                    for b,events in enumerate(outcome.tolist()):
                        for lane,ordinal in enumerate(events):
                            if ordinal and ordinal not in seen[b]:
                                seen[b].add(ordinal);release[b,lane]=1.
                    child=torch.from_numpy(release)
                    if arm=='team':
                        local=win.float()+child
                    else:
                        root_credit=torch.where(size[idx//8]>1,params[4],params[3]).float()
                        local=active.float()*min(0.,params[2])+win*root_credit+child*params[5]
                    team=local.sum(1)
                    # Run and presented-bank costs are action-independent for this fixed
                    # architecture and cancel in the advantage; still record them in net work.
                    charge=(params[0]+params[1]*present.sum(1))/4 if arm.startswith('weighted') else 0.
                    rewards.append(float((team+charge).mean()))
                    if arm=='weighted_cf':
                        # Hold the peer action fixed and replace this lane with abstention.
                        # With distinct primary keys, both lanes may still predict the same
                        # later RHS; that secondary result can only be counted once.
                        marginal=local.clone()
                        same=(outcome[:,0]==outcome[:,1])&(outcome[:,0]>0)
                        marginal[same,0]-=child[same,0]*params[5]
                        advantage=marginal
                    else:
                        advantage=(team-moving)[:,None].expand(-1,2)
                    policy_loss.append(-(logp*advantage.detach()).mean())
                    moving=.98*moving+.02*float(team.mean())
                    for lane in range(2):
                        reserved=reserved.scatter(1,idx[:,lane,None],
                            (reserved.gather(1,idx[:,lane,None])|active[:,lane,None]))
            loss=torch.stack(losses).mean()
            if arm!='supervised':loss=loss+.25*torch.stack(policy_loss).mean()
            opt.zero_grad();loss.backward();nn.utils.clip_grad_norm_(model.parameters(),1.);opt.step()
            if step%20==0:logs.append([step,float(loss.detach()),float(np.mean(rewards))])
        return logs
    updates(net,'supervised',a.warm,0)
    for arm in ('supervised','team','weighted','weighted_cf'):
        fitted=deepcopy(net);logs=updates(fitted,arm,a.updates,197)
        path=a.out/f'{seed}-{arm}';path.mkdir(parents=True,exist_ok=False)
        torch.save(fitted.state_dict(),path/'actor.pt')
        model=dict(source_weights,root=fitted.root.metal_weights(),head=fitted.native(),reward=arm,
                   static_waves=4,rows=2,warm=a.warm,finetuning_updates=a.updates,logs=logs)
        (path/'model.json').write_text(json.dumps(model,separators=(',',':'))+'\n')
        print(seed,arm,logs[-1],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('native','weights','donor','out'):p.add_argument(k,type=Path)
    p.add_argument('--warm',type=int,default=100);p.add_argument('--updates',type=int,default=160)
    a=p.parse_args()
    for seed in (1703,1709):train(a,seed)

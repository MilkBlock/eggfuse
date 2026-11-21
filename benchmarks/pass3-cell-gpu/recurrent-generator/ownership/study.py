"""On-policy port selection in the two-row recursive PyTorch generator."""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import torch
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from compound_model import CompoundActor
from model import HIDDEN, LEAVES, RANKS, ROWS
from ports import Port, Transfers


def actor_from_checkpoint():
    p=json.loads((HERE.parent/"pending/policy-continuation-1703.json").read_text())
    actor=CompoundActor(p["joins"],ownership_feedback=True)
    with torch.no_grad():
        for weights,params in [(p["roots"],actor.root.parameters()),(p["child"],
                [actor.score,actor.row_score,actor.embedding,actor.null,actor.row_latent])]:
            offset=0
            for par in params:
                end=offset+par.numel()
                par.copy_(torch.tensor(weights[offset:end]).reshape_as(par))
                offset=end
            assert offset==len(weights)
    return actor


def episode(actor, device, rng, n, leaf, previous, mode, mirror=False):
    # Two visible parent tokens with the same eligible type. Give them opaque,
    # pass-local token addresses. Both remain selectable after a transfer.
    def randint(end,*shape):
        return torch.randint(end,shape,generator=rng)
    obs=torch.zeros(n,LEAVES*RANKS,8)
    obs[:,:,0]=-1
    obs[:,leaf*RANKS,0]=randint(10000,n).float()
    obs[:,:,1]=2
    with torch.no_grad():
        _,parents=actor.root.step(obs.to(device),previous,score_adjust=torch.full((1,1,1),100.,device=device))
    assert (parents[:,:,HIDDEN]==leaf+1).all() and (parents[:,:,-1]==1).all()
    join=next(i for i,j in enumerate(actor.joins.tolist()) if j[1]==leaf)
    _,_,port,consumer=actor.joins[join].tolist()
    addresses=randint(20000,n,1)*2+torch.tensor([1,2])
    old_lanes=(randint(2,n)+int(mirror))%2
    roles=torch.zeros(n,2,len(actor.joins))
    ledgers=[]
    targets=[]
    for b,old in enumerate(old_lanes.tolist()):
        endpoints=[Port(int(k),port,1) for k in addresses[b]]
        src,dst=endpoints[old],endpoints[1-old]
        ledger=Transfers()
        ledger.publish(src,0)
        if mode=="move":
            ledger.transfer(src,dst,1)
            targets.append(1)
        else:
            ledger.publish(dst,1)
            targets.append(2)
            if mode=="other-port":
                # A real transfer on another effect of these same tokens.
                e=Port(src.token,port+1,1)
                ledger.publish(e,2)
                ledger.transfer(e,Port(dst.token,port+1,1),1)
        for row,e in enumerate(endpoints):
            roles[b,row,join]=ledger.role(e)
        ledgers.append(ledger)
    return parents,addresses.to(device),roles.to(device),ledgers,targets,consumer


def forward(actor, batch, *, sample, blind=False):
    parents,addresses,roles,ledgers,targets,consumer=batch
    n=len(parents)
    verdict=parents.new_zeros(n,ROWS,4)
    logits,child,action=actor.propose_children(parents,verdict,False,torch.ones(n,device=parents.device),
        ownership=torch.zeros_like(roles) if blind else roles,parent_addresses=addresses,sample=sample)
    logp=logits.log_softmax(-1).gather(-1,action[...,None]).squeeze(-1).sum(-1)
    counts=Counter()
    rewards=[]
    for ledger,tokens,target in zip(ledgers,child[:,:,HIDDEN:].detach().cpu().tolist(),targets):
        claims=[(Port(int(addr),int(port)-1,1),int(right)-1) for right,addr,port,active in tokens if active]
        z=ledger.audit(claims)
        assert all(right==consumer for _,right in claims)
        counts.update(z)
        counts["episodes"]+=1
        counts["required"]+=target
        counts["exact"]+=z["novel"]==target and z["active"]==target
        rewards.append(z["novel"]-z["retired"]-z["duplicate"]-z["unknown"])
    return child.detach(),logp,parents.new_tensor(rewards),counts


def run(a):
    torch.set_num_threads(1)
    torch.manual_seed(341)
    actor=actor_from_checkpoint().to(a.device)
    rng=torch.Generator().manual_seed(421)
    # Gradients enter the actual child/parent pointer logits before issuance.
    params=[actor.score,actor.row_score,actor.null,actor.port_gain,actor.null_gain]
    opt=torch.optim.Adam(params,lr=.045)
    n=48
    previous=torch.zeros(n,ROWS,HIDDEN+4,device=a.device)
    baselines={}
    for i in range(480):
        mode=["move","keep","move","other-port"][i%4]
        leaf=[25,2][(i//4+i)%2]
        batch=episode(actor,a.device,rng,n,leaf,previous,mode)
        previous,logp,reward,_=forward(actor,batch,sample=True)
        old=baselines.get((mode,leaf),0.)
        loss=-(logp*(reward-old)).mean()
        opt.zero_grad();loss.backward();opt.step()
        baselines[mode,leaf]=.85*old+.15*float(reward.mean())
    out={}
    with torch.no_grad():
        for leaf in (25,2,8):
            for mode in ("move","keep","other-port"):
                for blind in (False,True):
                    rng=torch.Generator().manual_seed(7861)
                    previous.zero_()
                    counts=Counter()
                    for i in range(8):
                        batch=episode(actor,a.device,rng,n,leaf,previous,mode)
                        previous,_,_,z=forward(actor,batch,sample=False,blind=blind)
                        counts.update(z)
                    out[f"{leaf}/{mode}/{'blind' if blind else 'aware'}"]=dict(counts)
    a.out.mkdir(exist_ok=True)
    (a.out/"results.json").write_text(json.dumps(dict(device=a.device,seed=341,updates=480,arms=out),indent=2)+"\n")
    tuned={k:v.detach().cpu().tolist() for k,v in actor.named_parameters() if any(v is p for p in params)}
    (a.out/"weights.json").write_text(json.dumps(tuned,indent=1)+"\n")
    print({k:(v["retired"],v["novel"],v["exact"]) for k,v in out.items() if k.startswith("25/")})


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("out",type=Path)
    p.add_argument("--device",choices=("mps","cpu"),default="mps")
    run(p.parse_args())

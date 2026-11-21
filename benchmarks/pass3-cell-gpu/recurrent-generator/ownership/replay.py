"""Audit published neural streams, then replay verified storage moves into child generation."""
import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
import torch

from ports import Port, Transfers
from study import HERE, HIDDEN, actor_from_checkpoint


def stream(folder):
    with np.load(folder/"neural-output.npz") as f:
        raw=f["raw"]
    with np.load(folder/"compound-output.npz") as f:
        claims=f["claims"]
    roots,children=raw[:,:2],raw[:,2:]
    t,lane=np.nonzero(children[:,:,-1])
    addr=children[t,lane,HIDDEN+1].astype(int)-1
    assert np.array_equal(addr//2,t)
    assert np.array_equal(addr%2,claims[t,lane,0])
    return [(torch.tensor(roots[run,peer]),int(effect)-1,int(right)-1)
            for run,peer,effect,right in zip(t,addr%2,children[t,lane,HIDDEN+2],children[t,lane,HIDDEN])],dict(active_children=len(t),same_run_parent=int((addr//2==t).sum()),
                      later_retired_or_overwritten=int((claims[t,lane,8]==3).sum()),
                      verifier_duplicate=int((claims[t,lane,8]==4).sum()),
                      post_transfer_rate=None)


def probe(actor,roots,action):
    # This adaptation supplies alternatives to the selector on a real parent
    # tensor; owner IDs here are an explicitly constructed token namespace.
    before=dict(action["members"])
    after=dict(action["new_members"])
    changed=[m for m in before if before[m]!=after[m]]
    assert len(changed)==1
    member=changed[0]
    old,new=before[member],after[member]
    assert old in action["retired_owners"]
    joins=actor.joins.tolist()
    tensors=roots
    assert tensors
    out={}
    for placement,order in (("old-first",[old,new]),("new-first",[new,old])):
        counts={k:Counter() for k in ("aware","blind")}
        for token,port,right in tensors:
            parents=token[None,None,:].expand(1,2,-1)
            leaf=int(token[HIDDEN])-1
            eligible=[(j,e,c) for j,(_,l,e,c) in enumerate(joins) if l==leaf]
            assert any(e==port and c==right for _,e,c in eligible)
            # The native log authenticates a whole-member move. Exposing that
            # member as this actor's chosen effect is a controlled interface.
            ledger=Transfers()
            version=action["epoch"]
            endpoints=[Port(owner,port,version) for owner in order]
            src,dst=Port(old,port,version),Port(new,port,version)
            ledger.publish(src,member)
            ledger.transfer(src,dst,action["run"])
            roles=torch.zeros(1,2,len(joins))
            for lane,e in enumerate(endpoints):
                for other in {effect for _,effect,_ in eligible if effect!=port}:
                    ledger.publish(Port(e.token,other,version),(member,lane,other))
                for j,effect,_ in eligible:
                    roles[0,lane,j]=ledger.role(Port(e.token,effect,version))
            for arm in counts:
                _,child,_=actor.propose_children(parents,torch.zeros(1,2,4),False,torch.tensor([action["run"]+1]),
                    ownership=roles if arm=="aware" else roles*0,parent_addresses=torch.tensor([order]))
                claims=[(Port(int(a),int(p)-1,version),int(r)-1) for r,a,p,on in child[0,:,HIDDEN:].tolist() if on]
                counts[arm].update(ledger.audit(claims))
                counts[arm]["current_requested"]+=sum(e==dst and c==right for e,c in claims)
                counts[arm]["current_requested_covered"]+=any(e==dst and c==right for e,c in claims)
        out[placement]={k:dict(v) for k,v in counts.items()}
    return dict(run=action["run"],member=member,old_owner=old,new_owner=new,
                parent_tensors=len(tensors),arms=out)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("paired",type=Path);p.add_argument("weights",type=Path);p.add_argument("out",type=Path)
    a=p.parse_args()
    torch.set_num_threads(1)
    actor=actor_from_checkpoint()
    with torch.no_grad():
        for name,value in json.loads(a.weights.read_text()).items():
            dict(actor.named_parameters())[name].copy_(torch.tensor(value))
        native=json.loads((HERE.parents[1]/"prospective-owner-placement/first.json").read_text())
        report={}
        for name in ("dot-product","stable-argmax","sum-bits","gemm-bias-relu"):
            roots,row=stream(a.paired/(name+"-1703-batch"))
            report[name]=dict(stream=row)
            if name in native:
                report[name]["intervention"]=probe(actor,roots,native[name]["defer/merge"]["action"])
        a.out.write_text(json.dumps(report,indent=2)+"\n")

"""Online issuance interventions on the same compiled recursive Cell generator."""
import argparse
import cProfile  # Load stdlib profile before the benchmark profile modules.
from collections import Counter
import json
from pathlib import Path
import random
from runpy import run_path

HERE=Path(__file__).resolve().parent
matrix=run_path(str(HERE.parent/"ripsat-publication-matrix/study.py"))
src=matrix["src"]
write=run_path(str(HERE.parent/"explicit-parent-cell-composition/ripsat_bridge.py"))["write_artifact"]


def setup(a,case):
    program,plans,request=src.config(a,case)
    donors={n:a.exp/"compact-holdouts-20261121-v1"/(n+"-1703")/"program.json" for n in ("dot-product","jacobi-1d")}
    cert=matrix["authorizer"]["load_checked"](matrix["AUTH"]/(case+".json"),
        HERE.parent/"ripsat-donor-evidence/evidence.json",donors,program)
    request["source_sha256"]=cert["target_sha256"]
    return program,plans,request,cert["strict_named"]


def emit(run,req,spec,mode,weights,seed=0,rows=None):
    actor=dict(mode=mode,weights=weights,seed=seed)
    cfg=matrix["cfg"](req,dict(spec,issuance_actor=actor),True)
    if rows is not None:
        cfg["generated_get_inputs"]=rows
    v=run(cfg)
    if "source_error" in v:
        raise ValueError(v["source_error"])
    return v


def generated(seed):
    rng=random.Random(seed)
    def eq(i):return {"sort":"Expr","eq":f"Value({i})"}
    def arg(i):return {"sort":"i64","value":i}
    def row(table,*values):return dict(table=table,values=values,subsumed=False)
    rows=[]
    for i in range(rng.randint(2,14)):
        t,y,z=eq(10*i),eq(10*i+1),eq(10*i+2)
        rows.append(row("Get",t,arg(rng.randrange(4)),y))
        if rng.random()<0.4:
            rows.append(row("Single",y,z))
            if rng.random()<0.5:rows.append(row("Get",z,arg(0),y))
    return rows


def packets(v):
    return sum(v["root_recipe"]["emitted"])+sum(int(r["selected"]) for r in v["merge_child"]["issued"])


def paired(leaf,chosen):
    for key in ("rhs","writes","resumes","state_sha","schedule","runs","events"):
        assert chosen[key]==leaf[key],key
    assert chosen["constructor_births"]["endpoint"]==leaf["constructor_births"]["endpoint"]
    links,_=matrix["native_controls"]["validate_links"](chosen,None)
    signed=chosen["strict_named"]["signed_commits"]
    assert not leaf["strict_named"]["signed_commits"]
    assert len({r[0] for r in signed})==len(signed)
    credit=Counter(root for _,root,*_ in signed)
    saved=packets(leaf)-packets(chosen)
    assert sum(credit.values())==saved
    return saved,credit,len(links)


def train(a):
    import os
    import torch
    if a.device=="mps" and os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK")!="0":
        raise ValueError("disable MPS fallback for GPU training")
    if not os.environ.get("EGGFUSE_GENERATED_GET_EPISODES"):
        raise ValueError("training needs an explicitly generated input environment")
    program,plans,req,spec=setup(a,"dot-product")
    weights=torch.nn.Parameter(torch.tensor([-0.5,0.,0.],device=a.device))
    opt=torch.optim.Adam([weights],lr=0.18)
    episodes=[]
    with src.base.session(a.native,program,plans) as run:
        for epoch in range(a.updates):
            features=[]; actions=[]; rewards=[]
            current=weights.detach().cpu().tolist()
            for j in range(4):
                seed=9029+epoch*4+j
                rows=generated(seed)
                leaf=emit(run,req,spec,"leaf",current,rows=rows)
                sample=emit(run,req,spec,"sample",current,seed,rows)
                saved,credit,terminals=paired(leaf,sample)
                decisions=sample["strict_named"]["issuance_actor"]["decisions"]
                selected={serial for serial,_,action in decisions if action}
                assert set(credit)<=selected
                episodes.append(dict(seed=seed,decisions=len(decisions),composed=len(selected),
                    leaf_packets=packets(leaf),sample_packets=packets(sample),savings=saved,terminal=terminals))
                for serial,x,action in decisions:
                    features.append(x);actions.append(float(action));rewards.append(credit[serial])
            if not features:raise ValueError("no eligible generated root tokens")
            x=torch.tensor(features,device=a.device)
            action=torch.tensor(actions,device=a.device)
            reward=torch.tensor(rewards,dtype=torch.float32,device=a.device)
            logits=x@weights
            loss=(reward.detach()*torch.nn.functional.binary_cross_entropy_with_logits(logits,action,reduction="none")).mean()
            opt.zero_grad();loss.backward();opt.step()
    if not sum(e["savings"] for e in episodes):raise ValueError("training observed no proposal savings")
    write(a.out/"actor.json",dict(schema="ripsat-issuance-actor/v1",training_device=str(weights.device),
        weights=weights.detach().cpu().tolist(),features=["bias","log_page_count","log_parent_age"],
        initial_weights=[-0.5,0.,0.],episodes=episodes))


def evaluate(a):
    policy=json.loads(a.checkpoint.read_bytes())
    if policy.get("schema")!="ripsat-issuance-actor/v1":raise ValueError("incorrect actor checkpoint")
    out={}
    for case in ("sum-bits","3mm"):
        program,plans,req,spec=setup(a,case)
        arms={}
        with src.base.session(a.exp/"compact-vanilla-20261121/vanilla-audit",program) as oracle:
            gold=oracle({"audit":True})
        with src.base.session(a.native,program,plans) as run:
            leaf=emit(run,req,spec,"leaf",policy["weights"])
            for name,mode,w in [("leaf","leaf",policy["weights"]),("initial","greedy",policy["initial_weights"]),
                    ("sample","sample",policy["weights"]),("learned","greedy",policy["weights"]),("full","full",policy["weights"])]:
                v=leaf if name=="leaf" else emit(run,req,spec,mode,w,713)
                saved,credit,terminals=paired(leaf,v)
                q,_=matrix["summarize"](v,gold,True)
                diag=v["strict_named"]["issuance_actor"]
                if mode=="sample":
                    assert set(credit)<={sid for sid,_,on in diag["decisions"] if on}
                arms[name]=dict(saved=saved,terminal=terminals,credited_roots=len(credit),token_actions=diag["tokens"],
                    packets=q["packets"],fept=q["fept"],final_origins=q["visible"],rhs=q["rhs"],runs=q["runs"],checks=q["checks"])
                print(case,name,saved,terminals,flush=True)
        out[case]=arms
        write(a.out/"results.json",out)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode",choices=["train","evaluate"])
    for k in ("exp","native","out"):p.add_argument(k,type=Path)
    p.add_argument("--checkpoint",type=Path)
    p.add_argument("--device",choices=["cpu","mps"],default="mps")
    p.add_argument("--updates",type=int,default=12)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    (train if a.mode=="train" else evaluate)(a)

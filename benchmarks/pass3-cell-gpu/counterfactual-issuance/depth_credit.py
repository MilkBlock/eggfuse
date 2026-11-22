"""Paired returns for the depth of a particular initial SubTuple root."""
import argparse
from collections import Counter
import json
from pathlib import Path
import random

import torch
from train import study, verify
from walk_credit import validate


def rows(seed, mask):
    rng=random.Random(seed)
    ids=rng.sample(range(1000000),6)
    eq=lambda v:dict(sort="Expr",eq=f"Value({v})")
    num=lambda v:dict(sort="i64",value=v)
    fact=lambda t,*vs:dict(table=t,values=list(vs),subsumed=False)
    src,out,element,nested,other,unused=map(eq,ids)
    start=num(rng.randrange(8))
    length=num(rng.randint(2,5))
    result=[fact("SubTuple",src,start,length,out),
            fact("Get",src if mask & 1 else other,start,element),
            fact("Single",element if mask & 2 else unused,nested)]
    rng.shuffle(result)
    return result


def state(rows):
    pivot=next(r["values"] for r in rows if r["table"]=="SubTuple")
    types=("Get","Single","SubTuple")
    features=[]
    for r in rows:
        values=r["values"]
        local=([float(r["table"]==t) for t in types]
               +[float(i<len(values) and values[i]==v) for i in range(4) for v in pivot]
               +[float(pivot[2]["value"])/5])
        # Role-specific equality messages from the other input tokens.
        for t in types:
            others=[q["values"] for q in rows if q is not r and q["table"]==t]
            local.extend(float(i<len(values) and "eq" in values[i] and any(
                j<len(v) and values[i]==v[j] for v in others))
                for i in range(4) for j in range(4))
        features.append(local)
    return torch.tensor(features)


def collect(args,case,start,n,choose=None):
    program,plans,req,spec=study["setup"](args,case)
    rules=json.loads(program.read_bytes())["recipe"]["rules"]
    first,last=spec["set_publication"]["path"]
    subroot,=[i for i,r in enumerate(rules) if r["metadata"]["name"].startswith("(rewrite (SubTuple expr a b) (Concat")]
    subone,=[i for i,r in enumerate(rules) if r["metadata"]["name"].startswith("(rewrite (SubTuple expr x 1)")]
    targets={"Get":first[0],"Single":first[2],"SubTuple":subone}
    edges={(i,j,targets[e["call"]["table"]]) for i in {subroot,subone,*targets.values()}
           for j,e in enumerate(rules[i]["effects"]) if e["op"] in ("set","let") and e.get("call",{}).get("table") in targets}
    lib={(e,) for e in edges}|{(e,t) for e in edges for t in edges if e[2]==t[0] and [list(e),list(t)]!=[first,last]}
    cfg=dict(spec,library=sorted(lib),depth=8,pair_walk=True,set_edges=True,reuse_let=True,reuse_returns=True,
             literal_consumers=True,block_verifier=True,receipt_scan=2,issuance_actor=dict(mode="full",weights=[0.]*3,seed=0))
    examples=[]
    with study["src"].base.session(args.native,program,plans) as run:
        for i in range(n):
            initial=rows(start+i//4,i%4)
            x=state(initial)
            def play(limit):
                options=dict(cfg,root_limit=[subroot,1,limit])
                v=run(dict(study["matrix"]["cfg"](req,options,True),generated_get_inputs=initial))
                if v.get("source_error"):
                    raise ValueError(v["source_error"])
                validate(v,options)
                if len(v["strict_named"]["limited_roots"])!=1:
                    raise ValueError("depth action must control exactly the initial subject")
                return v
            selected=choose(x) if choose else None
            live=play(8 if selected else 2) if selected is not None else None
            shallow,deep=play(2),play(8)
            exact=run(dict(baseline=True,audit=True,generated_get_inputs=initial))
            for k in ("rhs","writes","state_sha","schedule","events","resumes","runs"):
                if shallow[k]!=exact[k]:raise ValueError((i,k))
            verify(shallow,deep)
            p=[study["packets"](v) for v in (shallow,deep)]
            links=[v["strict_named"]["signed_commits"] for v in (shallow,deep)]
            if p[0]-p[1]!=len(links[1])-len(links[0]):
                raise ValueError("depth credits differ from commits")
            def controlled(link):
                return link[2][0][0]==subroot and link[3][0][-1]==1
            if any(len(link[2])>2 and controlled(link) for link in links[0]):
                raise ValueError("escaped signed limit")
            if live is not None:
                verify(shallow,live)
                if study["packets"](live)!=p[int(selected)]: raise ValueError("live action mismatch")
            examples.append((x,p,selected))
    return examples


def fit(train, width, device, hidden=16):
    torch.manual_seed(1703)
    enc=torch.nn.Sequential(torch.nn.Linear(width,hidden),torch.nn.Tanh()).to(device)
    head=torch.nn.Linear(hidden,1).to(device)
    opt=torch.optim.Adam([*enc.parameters(),*head.parameters()],lr=.03)
    x=torch.stack([x[:,:width] for x,_,_ in train]).to(device)
    y=torch.tensor([p[0]-p[1] for _,p,_ in train],dtype=torch.float,device=device)
    for _ in range(400):
        opt.zero_grad()
        (head(enc(x).amax(1)).flatten()-y).square().mean().backward()
        opt.step()

    enc.cpu().eval()
    head.cpu().eval()

    @torch.no_grad()
    def choose(x):
        return head(enc(x[:,:width]).amax(0)).item()>=.5
    return choose


def main(args):
    train=collect(args,"dot-product",75100,256)
    width=train[0][0].shape[1]
    policy=fit(train,width,args.device)
    test=collect(args,"sum-bits",83200,64,policy)
    ablations={}
    for name,count,dim in (("local64",64,20),("local256",256,20),("links64",64,width)):
        alternate=fit(train[:count],dim,args.device)
        ablations[name]=sum(p[int(alternate(x))] for x,p,_ in test)
    # Match and slightly exceed the linked encoder's trainable parameter count
    # while retaining only subject-relative inputs.
    wide_local=fit(train,20,args.device,hidden=52)
    ablations["local256_wide"]=sum(p[int(wide_local(x))] for x,p,_ in test)
    report=dict(training_device=args.device,inference_device="cpu",samples=len(test),ablations=ablations,train_gains=dict(Counter(p[0]-p[1] for _,p,_ in train)),
                test_gains=dict(Counter(p[0]-p[1] for _,p,_ in test)),deep_selections=sum(c for _,_,c in test),
                shallow=sum(p[0] for _,p,_ in test),deep=sum(p[1] for _,p,_ in test),
                learned=sum(p[int(c)] for _,p,c in test))
    print(report,flush=True)
    (args.out/"depth-credit.json").write_text(json.dumps(report,indent=2)+"\n")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ("exp","native","out"):parser.add_argument(key,type=Path)
    parser.add_argument("--device",choices=("cpu","mps"),default="mps")
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    torch.set_num_threads(1)
    main(args)

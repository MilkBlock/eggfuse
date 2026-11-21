"""Train sequential extension decisions on generated source episodes, evaluate frozen policy."""
import argparse
import cProfile
import json
import os
from pathlib import Path
from runpy import run_path
from statistics import median

HERE = Path(__file__).resolve().parent
base = run_path(str(HERE.parent / "ripsat-issuance-rl/study.py"))
cfg = base["matrix"]["cfg"]
N = 7


def spec(plan, mode, weights, seed=0):
    return dict(plan, receipt_scan=2, block_verifier=True,
                scale_policy=dict(mode=mode, weights=weights, seed=seed))


def run_episode(run, req, plan, mode, weights, seed, rows):
    request = cfg(req, spec(plan, mode, weights, seed), True)
    v = run(dict(request, generated_get_inputs=rows))
    if "source_error" in v:
        raise ValueError(v["source_error"])
    return v


def returns(sample, nfields, price):
    sig = sample["strict_named"]
    reached = set()
    for _, root, path, *_ in sig["signed_commits"]:
        key = (root, len(path)-1)
        assert key not in reached
        reached.add(key)
    trace = sig["scale_policy"]["trace"]
    taken = {(root, step) for root, step, _, action in trace if action}
    assert reached <= taken
    # One independent proposal plus one address check and the projected fields
    # on each bypassed generic bind. A reservation price is a policy budget.
    reads = {(r,s):n for r,s,n in sig["scale_policy"]["receiver_reads"]}
    assert reads.keys() <= taken
    assert sum(reads.values()) == sig["receipt_scan"]["row_reads"]
    admissions = set(sig["scale_policy"]["admitted"])
    assert len(admissions)==sig["set_publication"]["admissions"]
    assert all((root,0) in taken for root in admissions)
    tail = {}
    data = []
    for root, step, x, action in reversed(trace):
        immediate = (2+nfields[step]) * ((root, step) in reached) - reads.get((root,step),0) - (step==0 and root in admissions) - price*action
        value = immediate + tail.get(root, 0.)
        tail[root] = value
        data.append((step, x, float(action), value))
    return data, sum(tail.values())


def train(a):
    import torch
    if a.device == "mps" and os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") != "0":
        raise ValueError("set PYTORCH_ENABLE_MPS_FALLBACK=0")
    program, plans, req, plan = base["setup"](a, "dot-product")
    rules = json.loads(program.read_bytes())["recipe"]["rules"]
    fields = [len(rules[edge[2]]["query"][0]["args"]) for edge in plan["set_publication"]["path"]]
    weights = torch.nn.Parameter(torch.zeros(N, device=a.device))
    opt = torch.optim.Adam([weights], lr=.12)
    baseline = [0.]*len(fields)
    history = []
    with base["src"].base.session(a.native, program, plans) as run:
        for epoch in range(36):
            batch = []
            utility = 0.
            w = weights.detach().cpu().tolist()
            for j in range(4):
                seed = 37003+epoch*4+j
                rows = base["generated"](seed)
                leaf = run_episode(run,req,plan,"leaf",w,seed,rows)
                sampled = run_episode(run,req,plan,"sample",w,seed,rows)
                base["paired"](leaf,sampled)
                data, u = returns(sampled, fields, a.price)
                actual = base["packets"](leaf)-base["packets"](sampled)
                actual += leaf["root_recipe"]["root_header_checks"]-sampled["root_recipe"]["root_header_checks"]
                actual -= sampled["strict_named"]["receipt_scan"]["row_reads"]-leaf["strict_named"]["receipt_scan"]["row_reads"]
                actual -= sampled["strict_named"]["set_publication"]["admissions"]
                chosen=sampled["strict_named"]["scale_policy"]["choices"]
                assert abs(actual-a.price*(chosen[1]+2*chosen[2])-u)<1e-6
                batch.extend(data)
                utility += u
            steps, x, acts, target = zip(*batch)
            logits = torch.tensor(x, device=a.device) @ weights
            advantages = torch.tensor([r-baseline[s] for s,r in zip(steps,target)],device=a.device)
            cost = torch.nn.functional.binary_cross_entropy_with_logits(
                logits,torch.tensor(acts,device=a.device),reduction="none")
            loss = (cost*advantages).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
            for s in range(len(fields)):
                seen = [r for z,r in zip(steps,target) if z==s]
                if seen:
                    baseline[s] = .8*baseline[s]+.2*sum(seen)/len(seen)
            history.append(dict(epoch=epoch, decisions=len(batch), utility=utility))
    a.output.write_text(json.dumps(dict(schema="ripsat-scale-policy/v1", weights=weights.detach().cpu().tolist(),price=a.price,
        fields=fields, device=a.device,updates=history),indent=2)+"\n")


def evaluate(a):
    model = json.loads(a.checkpoint.read_text())
    weights = model["weights"]
    results = {}
    for case in ("sum-bits","3mm"):
        p, plans, req, plan = base["setup"](a,case)
        with base["src"].base.session(a.exp/"compact-vanilla-20261121/vanilla-audit",p) as oracle:
            gold=oracle({"audit":True})
        arms={}
        configs={m:cfg(req,spec(plan,m,weights)) for m in ("leaf","prefix","full","greedy")}
        old = json.loads((HERE.parent/"ripsat-issuance-rl/actor.json").read_text())
        previous = dict(plan,receipt_scan=2,block_verifier=True,
                        issuance_actor=dict(mode="greedy",weights=old["weights"],seed=0))
        configs["previous"] = cfg(req,previous)
        with base["src"].base.session(a.native,p,plans) as run:
            for mode in configs:
                v=run(cfg(req,previous if mode=="previous" else spec(plan,mode,weights),True))
                result,_=base["matrix"]["summarize"](v,gold,True)
                sig=v["strict_named"]
                root=v["root_recipe"]
                choices=sig["scale_policy"]["choices"] if mode!="previous" else [
                    sig["issuance_actor"]["tokens"][0],0,sig["issuance_actor"]["tokens"][1]]
                arcs=choices[1]+2*choices[2]
                counts=sig["set_publication"]
                first=result["ordinary_let_internal"]
                second=result["set_internal"]
                assert counts["direct_binds"]==first+second
                assert mode!="prefix" or (first>0 and second==0)
                probes=sum(n*(1+f) for n,f in zip((first,second),model["fields"]))
                arms[mode]=dict(choices=choices,edges=arcs,first=first,second=second,
                    header_checks=root["root_header_checks"],bypassed_bind_probes=probes,
                    packets=result["packets"],rhs=result["rhs"],runs=result["runs"],
                    checks=result["checks"],fept=result["fept"],rejects=root["rejected"],
                    admissions=counts["admissions"], receipt_reads=sig["receipt_scan"]["row_reads"],
                    residual=len(root["commits"])-len(v["single"]["committed"])-len(v["multi"]["tickets"]),
                    utility=first+second+probes-sig["receipt_scan"]["row_reads"]-counts["admissions"]-model["price"]*arcs,ms=[])
                assert arms[mode]["residual"]==0
                assert arms["leaf"]["header_checks"]-root["root_header_checks"]==probes
                assert arms["leaf"]["packets"]-result["packets"]==first+second
            arms["exact"]=dict(ms=[])
            configs["exact"]={"baseline":True}
            for lap in range(6):
                names=list(configs)
                for mode in names[lap%len(names):]+names[:lap%len(names)]:
                    v=run(configs[mode])
                    assert v["state_sha"]==gold["state_sha"] and v["runs"]==gold["runs"]
                    if lap: arms[mode]["ms"].append(v["ms"])
            for arm in arms.values(): arm["median_ms"]=median(arm["ms"])
        results[case]=arms
        a.output.write_text(json.dumps(results,indent=2)+"\n")
        print(case, {k:(v.get("choices"),v.get("utility"),v["median_ms"]) for k,v in arms.items()},flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=["train","evaluate"])
    for k in ("exp","native","output"):
        parser.add_argument(k,type=Path)
    parser.add_argument("--device",choices=["mps","cpu"],default="mps")
    parser.add_argument("--checkpoint",type=Path)
    parser.add_argument("--price",type=float,default=0.)
    a=parser.parse_args()
    a.out=a.output.parent
    (train if a.mode=="train" else evaluate)(a)

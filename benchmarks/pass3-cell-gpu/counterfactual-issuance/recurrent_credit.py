"""Collect native action values after earlier tokens have already executed."""
from collections import Counter
import random

import torch

from route_credit import continuation_edges
from train import study, verify
import json


def collect(args, reader, episodes=48):
    program, plans, req, spec = study["setup"](args, "dot-product")
    single, sub = continuation_edges(json.loads(program.read_bytes())["recipe"], spec)
    opts = dict(spec, library=[[single], [sub]], literal_consumers=True,
                reuse_returns=True, block_verifier=True, receipt_scan=2,
                issuance_actor=dict(mode="full", weights=[0.,0.,0.], seed=0))
    policy = dict(reader, edges=[single, sub], training_fork=True)
    samples = []
    runs, gains = Counter(), Counter()
    with study["src"].base.session(args.native,program,plans) as run:
        for i in range(episodes):
            seed = 194700+i
            rng = random.Random(seed)
            rows = study["generated"](seed)
            # Existing SubTuple keys can change whether its continuation is productive.
            for j, row in enumerate(rows.copy()):
                if row["table"] == "Get" and rng.randrange(2):
                    result = {"sort":"Expr","eq":f"Value({1000000+j})"}
                    rows.append(dict(table="SubTuple",subsumed=False,values=[
                        *row["values"][:2], {"sort":"i64","value":1}, result]))
            rng.shuffle(rows)
            def play(force=None):
                model = policy if force is None else dict(policy,force=force)
                request = study["matrix"]["cfg"](req,dict(opts,route_reader=model),True)
                data = run(dict(request,generated_get_inputs=rows))
                if data.get("source_error"):
                    raise ValueError(data["source_error"])
                return data

            full = play()
            exact = run(dict(baseline=True,audit=True,generated_get_inputs=rows))
            for key in ("resumes","events","rhs","writes","runs","state_sha","schedule"):
                if full[key] != exact[key]:
                    raise ValueError(("training source",seed,key))
            observations = full["strict_named"]["route_observations"]
            full_signed = {r[0] for r in full["strict_named"]["signed_commits"]}
            for epoch in sorted({r[1] for r in observations}):
                pos = rng.choice([j for j,r in enumerate(observations) if r[1]==epoch])
                serial, _, signatures = observations[pos]
                paid = []
                for action in range(4):
                    arm = full if action==3 else play([serial,action])
                    verify(full,arm)
                    histogram, _ = arm["strict_named"]["route_choices"]
                    if (action < 3 and (histogram[action]!=1 or sum(histogram[:3])!=1)
                            or action==3 and sum(histogram[:3])!=0):
                        raise ValueError("override did not select exactly one signed route")
                    obs = arm["strict_named"]["route_observations"]
                    if obs[:pos+1]!=observations[:pos+1]:
                        raise ValueError("intervention changed the observation prefix")
                    paid.append(study["packets"](arm))
                    signed = {r[0] for r in arm["strict_named"]["signed_commits"]}
                    if paid[-1]-study["packets"](full)!=len(full_signed)-len(signed):
                        raise ValueError("unaccounted intervention")
                x = torch.tensor([[float((key>>bit)&1) for bit in range(15)] for key in signatures])
                samples.append((x,paid,epoch))
                gains[tuple(paid[0]-p for p in paid[1:])]+=1
                runs[epoch]+=1
    if len(runs)<2:
        raise ValueError("no post-initial decisions")
    return samples, dict(decision_runs=dict(runs), marginal_gains={str(k):v for k,v in gains.items()})

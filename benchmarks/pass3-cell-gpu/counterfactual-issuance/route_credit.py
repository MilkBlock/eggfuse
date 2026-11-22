"""Compare two licensed first-root continuations and their combined action."""
import argparse
import json
from pathlib import Path

import torch

from context_credit import inputs
from train import study, verify


def episode_rows(seed, mask):
    rows = inputs(seed, seed % 4, mask & 1)
    get = next(r["values"] for r in rows if r["table"] == "Get")
    def integer(v):
        return {"sort": "i64", "value": v}
    def identity(i):
        return {"sort": "Expr", "eq": f"Value({1000000 + 2*seed+i})"}
    rows.insert(seed % len(rows), dict(table="SubTuple", subsumed=False,
                values=[get[0] if mask & 2 else identity(0), get[1], integer(1), identity(1)]))
    return rows


def features(rows):
    subject = next(r["values"] for r in rows if r["table"] == "Get")
    tokens = []
    for row in rows:
        vs = row["values"]
        tokens.append([float(row["table"] == t) for t in ("Get", "Single", "SubTuple")]
                      + [float(i < len(vs) and vs[i] == v) for i in range(4) for v in subject])
    return torch.tensor(tokens)


def continuation_edges(recipe, spec):
    single = spec["set_publication"]["path"][0]
    root = single[0]
    op, = [i for i, effect in enumerate(recipe["rules"][root]["effects"])
           if effect.get("kind") == "construct" and effect["call"].get("table") == "SubTuple"
           and effect["args"][2].get("literal") == 1]
    rid, = [i for i, rule in enumerate(recipe["rules"])
            if rule["metadata"]["source_set"] == "always-run" and len(rule["query"]) == 1
            and rule["query"][0]["call"].get("table") == "SubTuple"
            and rule["query"][0]["args"][2].get("literal") == 1]
    return single, [root, op, rid]


def run_split(args, case, start, count, policy=None):
    program, plans, req, spec = study["setup"](args, case)
    single, sub = continuation_edges(json.loads(program.read_bytes())["recipe"], spec)
    branches = [[], [single], [sub], [single, sub]]
    cfg = dict(spec, library=[[single],[sub]], block_verifier=True, reuse_returns=True,
               literal_consumers=True, receipt_scan=2)
    examples = []
    with study["src"].base.session(args.native, program, plans) as run:
        for i in range(count):
            rows = episode_rows(start+i//4, i%4)
            x = features(rows)
            chosen = policy(x) if policy else None
            def execute(edges):
                actor = dict(mode="first_context", weights=[1.,0.,0.], seed=0)
                config = study["matrix"]["cfg"](req,dict(cfg,first_edges=edges,issuance_actor=actor),True)
                result = run(dict(config, generated_get_inputs=rows))
                if result.get("source_error"):
                    raise ValueError(result["source_error"])
                return result
            live = execute(branches[chosen]) if chosen is not None else None
            baseline = execute([])
            exact = run(dict(baseline=True,audit=True,generated_get_inputs=rows))
            for k in ("rhs","writes","resumes","state_sha","schedule","runs","events"):
                if baseline[k] != exact[k]:
                    raise ValueError((case,i,k))
            paid = []
            for edges in branches:
                arm = execute(edges) if edges else baseline
                verify(baseline, arm)
                serial = arm["strict_named"]["issuance_actor"]["decisions"][0][0]
                sig = arm["strict_named"]["signed_commits"]
                if any(s[1] != serial or s[2][0] not in edges for s in sig):
                    raise ValueError("wrong signed root or continuation")
                paid.append(study["packets"](arm))
                if paid[0]-paid[-1] != len({s[0] for s in sig}):
                    raise ValueError("uncredited proposal")
            if live:
                verify(baseline, live)
                if study["packets"](live) != paid[chosen]:
                    raise ValueError("live prediction diverged")
            examples.append((x, paid, chosen))
    return examples


def fit(train, hidden, steps, export=None):
    torch.manual_seed(17)
    encoder = torch.nn.Sequential(torch.nn.Linear(15, hidden), torch.nn.Tanh())
    head = torch.nn.Linear(hidden, 3)
    opt = torch.optim.Adam([*encoder.parameters(), *head.parameters()], lr=.025)
    y = torch.tensor([[p[0]-p[i] for i in (1, 2, 3)] for _, p, _ in train], dtype=torch.float)
    # Max pooling is invariant to padding by duplicating a real token.
    width = max(len(x) for x, _, _ in train)
    batch = torch.stack([torch.cat([x, x[:1].expand(width-len(x), -1)]) for x, _, _ in train])
    for _ in range(steps):
        opt.zero_grad()
        (head(encoder(batch).amax(dim=1))-y).square().mean().backward()
        opt.step()

    if export is not None:
        export.update(encoder=encoder[0].weight.tolist(), bias=encoder[0].bias.tolist(),
                      head=head.weight.tolist(), out=head.bias.tolist())

    @torch.no_grad()
    def scores(x):
        return head(encoder(x).amax(dim=0))

    return scores


def choose(scores, x):
    # Integers are the units of the reward. Prefer the smaller action at a tie.
    gains = torch.cat([torch.zeros(1), scores(x).round()])
    return gains.argmax().item()


def main(args):
    train = run_split(args, "dot-product", 84700, args.quartets*4)
    scores = fit(train, 24, 500)
    test = run_split(args, "sum-bits", 95700, args.quartets*4, lambda x: choose(scores, x))
    report = dict(episodes=len(test),paid=dict(zip(("leaf","single","subtuple","both"),
                       map(sum,zip(*(p for _,p,_ in test))))),
                  learned_uses_both=sum(c==3 for _,_,c in test),
                  learned_paid=sum(p[c] for _,p,c in test),
                  learned_single_only_paid=sum(p[int(scores(x)[:2].detach().argmax())+1] for x,p,_ in test),
                  best_one_paid=sum(min(p[1:3]) for _,p,_ in test),
                  first_better=sum(p[1]<p[2] for _,p,_ in test),
                  second_better=sum(p[2]<p[1] for _,p,_ in test))
    report["ablations"] = {}
    for name, subset, width, steps in (
            ("one_quartet", train[:4], 24, 500),
            ("one_outcome_per_quartet", train[::4], 24, 500),
            ("four_quartets", train[:16], 24, 500),
            ("four_hidden_units", train, 4, 500),
            ("eight_updates", train, 24, 8)):
        alternate = fit(subset, width, steps)
        report["ablations"][name] = dict(
            paid=sum(p[choose(alternate,x)] for x,p,_ in test),
            all_gains_correct=sum(alternate(x).round().tolist() == [p[0]-v for v in p[1:]]
                                  for x,p,_ in test))
    print(report,flush=True)
    (args.out/"route-credit.json").write_text(json.dumps(report,indent=2)+"\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for field in ("exp","native","out"):
        p.add_argument(field,type=Path)
    p.add_argument("--quartets",type=int,default=16)
    args = p.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    torch.set_num_threads(1)
    main(args)

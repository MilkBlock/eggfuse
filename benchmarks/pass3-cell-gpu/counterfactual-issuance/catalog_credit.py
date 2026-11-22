"""Isolate paid-token credit and the action-library ceiling on native EggCC."""
import argparse
import json
from collections import Counter
from pathlib import Path
from runpy import run_path

import torch
from train import study

here = Path(__file__).resolve().parent
expand = run_path(str(here.parent / "filtered-explicit-parent/complete_library.py"))["extend"]


def fit(pairs):
    # Every pair starts at the same native decision in a randomly generated program.
    x = torch.tensor([p["x"] for p in pairs])
    gains = torch.tensor([p["leaf"]["paid"] - p["full"]["paid"] for p in pairs], dtype=torch.float)
    weights = torch.nn.Parameter(torch.zeros(x.shape[1]))
    opt = torch.optim.Adam([weights], lr=.1)
    for _ in range(160):
        loss = -(torch.sigmoid(x @ weights) * gains).mean()
        opt.zero_grad()
        loss.backward()
        opt.step()
    return weights.tolist(), dict(sorted(Counter(map(int, gains.tolist())).items()))


def main(a):
    torch.set_num_threads(1)
    a.out.mkdir(parents=True, exist_ok=True)
    w, histogram = fit(json.loads(a.training.read_bytes())["pairs"])
    lib = json.loads((here.parent / "filtered-explicit-parent/library.json").read_bytes())
    report = dict(training_paid_gain=histogram, weights=w, cases={})
    if a.live:
        from route_credit import run_split, fit as fit_reader
        reader = {}
        initial = run_split(a,"dot-product",84700,64)
        fit_reader(initial,24,500,export=reader)
        if a.recurrent:
            from recurrent_credit import collect
            later, evidence = collect(a,reader)
            recurrent = {}
            fit_reader(initial+later,24,500,export=recurrent)
            first = [s for s in later if s[2]==1]
            post = [s for s in later if s[2]>1]
            balanced = first[:max(0,len(first)-len(post))] + post[:len(first)]
            first_model, mixed_model = {}, {}
            fit_reader(initial+first,24,500,export=first_model)
            fit_reader(initial+balanced,24,500,export=mixed_model)
            evidence["additional_samples"] = dict(first_only=len(first),mixed=len(balanced),all=len(later))
            report["generated_interventions"]=evidence
            (a.out/"recurrent-model.json").write_text(json.dumps(recurrent)+"\n")
        (a.out/"route-model.json").write_text(json.dumps(reader)+"\n")
    for case in a.cases:
        program, plans, req, spec = study["setup"](a, case)
        matrix = study["matrix"]
        catalog, _ = matrix["libraries"](a.exp, program, case)
        _, index = matrix["bake"].base["schema_map"](program)
        expanded = expand(program, index, lib["1"]["consumers"])
        combined = dict(catalog["union"])
        paths = {tuple(map(tuple, path)) for path in combined["library"]}
        paths.update((tuple(edge),) for edge in expanded)
        combined["library"] = sorted(paths)
        with study["src"].base.session(a.exp/"compact-vanilla-20261121/vanilla-audit",program) as run:
            exact = run({"audit":True})
        recipe = json.loads(program.read_bytes())["recipe"]
        ctors = {t["name"] for t in recipe["tables"] if t["kind"] == "constructor"}
        targets = []
        for signature, rid in index.items():
            rule = recipe["rules"][rid]
            query = rule["query"]
            if len(query) != 1 or not rule["metadata"]["seminaive"]:
                continue
            args = query[0]["args"]
            if (query[0]["call"].get("table") in ctors and all("slot" in a for a in args)
                    and len({a["slot"] for a in args}) == len(args)):
                targets.append(signature)
        edges = [tuple(edge) for edge in expand(program,index,targets)]
        by_root = {}
        for edge in edges:
            by_root.setdefault(edge[0], []).append(edge)
        wide_paths = paths | {(edge,) for edge in edges}
        wide_paths.update((edge, tail) for edge in edges for tail in by_root.get(edge[2], []))
        wide = dict(combined,library=sorted(wide_paths))
        let_only = {k:v for k,v in wide.items() if k != "set_publication"}
        guarded = []
        if a.literal:
            from route_credit import continuation_edges
            _, sub = continuation_edges(recipe, spec)
            first = (tuple(sub),)
            guarded = [("guarded_union",dict(wide,library=sorted(wide_paths | {first}),
                       literal_consumers=True,reuse_returns=True),"greedy")]
            guarded_tables = {}
            for consumer, rule in enumerate(recipe["rules"]):
                q = rule["query"]
                if not rule["metadata"]["seminaive"] or len(q) != 1 or q[0]["call"].get("table") not in ctors:
                    continue
                slots = [a["slot"] for a in q[0]["args"] if "slot" in a]
                literals = {i:a for i,a in enumerate(q[0]["args"]) if "slot" not in a}
                if (len(set(slots)) != len(slots) or not literals
                        or any(a.get("sort",{}).get("kind") != "i64" or "literal" not in a for a in literals.values())):
                    continue
                guarded_tables.setdefault(q[0]["call"]["table"], []).append((consumer,literals))
            eligible = set(edges)
            for producer, rule in enumerate(recipe["rules"]):
                for op, ins in enumerate(rule["effects"]):
                    if ins.get("kind") != "construct":
                        continue
                    for consumer, literals in guarded_tables.get(ins["call"].get("table"), []):
                        if all(i < len(ins["args"]) and ("slot" in ins["args"][i] or
                               ins["args"][i].get("literal") == a["literal"]) for i,a in literals.items()):
                            eligible.add((producer,op,consumer))
            tails = {}
            for edge in eligible:
                tails.setdefault(edge[0], []).append(edge)
            all_paths = wide_paths | {(e,) for e in eligible}
            all_paths.update((e,t) for e in eligible for t in tails.get(e[2], []))
            guarded.append(("all_literal",dict(wide,library=sorted(all_paths),
                            literal_consumers=True,reuse_returns=True),"greedy"))
        if a.live:
            _, cfg, _ = guarded[-1]
            from route_credit import continuation_edges
            route_edges = continuation_edges(recipe, spec)
            guarded.extend((name,dict(cfg,route_reader=dict(reader,edges=route_edges,single_only=one)),"full")
                           for name,one in (("live_one",True),("live_both",False)))
            if a.recurrent:
                for name, model in (("live_first_extra",first_model),("live_equal_mixed",mixed_model),
                                    ("live_recurrent",recurrent)):
                    guarded.append((name,dict(cfg,route_reader=dict(model,edges=route_edges)),"full"))
                if a.expected:
                    guarded.append(("expected_gain",dict(cfg,route_reader=dict(recurrent,
                                    expected_gain=True,edges=route_edges)),"full"))
        baseline = None
        results = {}
        with study["src"].base.session(a.native,program,plans) as run:
            for name, cfg, mode in (("leaf",catalog["leaf"],None),("original",spec,"greedy"),
                                    ("union",catalog["union"],"greedy"),("expanded",combined,"greedy"),
                                    ("wide_let_only",let_only,None),("wide",wide,"greedy"),("fixed_full",wide,"full"),
                                    *((("reuse_returns",dict(wide,reuse_returns=True),"greedy"),) if a.reuse_returns else ()), *guarded):
                if a.live and name not in ("leaf","all_literal","live_one","live_both","live_first_extra","live_equal_mixed","live_recurrent","expected_gain"):
                    continue
                if a.expected and name not in ("leaf","all_literal","live_recurrent","expected_gain"):
                    continue
                cfg = dict(cfg)
                if mode:
                    cfg.update(issuance_actor=dict(mode=mode, weights=w, seed=0),
                               block_verifier=True, receipt_scan=2)
                data = run(matrix["cfg"](req,cfg,True))
                counts, ledger = matrix["summarize"](data,exact,bool(mode))
                if baseline is None:
                    baseline = counts
                for key in matrix["FIXED"]:
                    if counts[key] != baseline[key]:
                        raise ValueError((case,name,key))
                paid = study["packets"](data)
                saved = baseline["packets"] - paid
                if saved != len(ledger[0]) or paid != counts["packets"]:
                    raise ValueError((case,name,"unattributed packet"))
                results[name] = dict(paid=paid, saved=saved, visible=counts["visible"], fept=counts["fept"],
                                     terminal=counts["set_internal"], checks=counts["checks"],
                                     paths=len(cfg.get("library",[])), state_sha=counts["state_sha"])
                if "route_reader" in cfg:
                    choices, runs = data["strict_named"]["route_choices"]
                    if not sum(choices) or runs < 2:
                        raise ValueError((case,name,"reader did not execute across Runs"))
                    results[name].update(choices=choices,decision_runs=runs)
                    if "route_fallback" in data["strict_named"]:
                        results[name]["fallback"]=data["strict_named"]["route_fallback"]
                if name=="reuse_returns":
                    captures=data["strict_named"]["actual_reused_returns"]
                    used={(r[1],tuple(r[2][0]),tuple(r[3][0]))
                          for r in data["strict_named"]["signed_commits"] if len(r[2])==1}
                    results[name]["reuse_registered"]=len(captures)
                    results[name]["reuse_committed"]=sum(
                        (r[0],tuple(r[1:4]),tuple(r[5:])) in used for r in captures)
                print(case,name,paid,saved,flush=True)
        report["cases"][case] = results
        (a.out/"catalog-credit.json").write_text(json.dumps(report,indent=2)+"\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("exp","native","training","out"):
        p.add_argument(key,type=Path)
    p.add_argument("--cases",nargs="+",default=["sum-bits","3mm"])
    p.add_argument("--reuse-returns",action="store_true")
    p.add_argument("--literal",action="store_true")
    p.add_argument("--live",action="store_true")
    p.add_argument("--recurrent",action="store_true")
    p.add_argument("--expected",action="store_true")
    args=p.parse_args()
    args.recurrent |= args.expected
    args.live |= args.recurrent
    args.literal |= args.live
    main(args)

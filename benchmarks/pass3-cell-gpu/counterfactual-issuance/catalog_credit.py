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
        if a.walk:
            _, base_cfg, _ = guarded[-1]
            for depth, reuse in ((8,False),(2,True),(4,True),(8,True),(32,True)):
                guarded.append((f"walk{depth}_reuse{int(reuse)}",
                                dict(base_cfg,depth=depth,pair_walk=True,reuse_let=reuse),"full"))
        if a.set_edges:
            typed_set = tuple(map(tuple,spec["set_publication"]["path"]))
            set_targets = {table:{consumer for consumer,_ in consumers}
                           for table,consumers in guarded_tables.items()}
            for signature in targets:
                consumer = index[signature]
                table = recipe["rules"][consumer]["query"][0]["call"]["table"]
                set_targets.setdefault(table,set()).add(consumer)
            set_edges = set()
            for rid, rule in enumerate(recipe["rules"]):
                for op, ins in enumerate(rule["effects"]):
                    if ins["op"] != "set":
                        continue
                    for target in set_targets.get(ins["call"].get("table"),()):
                        fields = [*ins["args"],ins["value"]]
                        patterns = recipe["rules"][target]["query"][0]["args"]
                        if len(fields)==len(patterns) and all("slot" in p or "slot" in f or
                                p["literal"]==f["literal"] for p,f in zip(patterns,fields)):
                            set_edges.add((rid,op,target))
            outgoing = {}
            for e in eligible | set_edges:
                outgoing.setdefault(e[0],[]).append(e)
            combined_paths = all_paths | {(e,) for e in set_edges}
            combined_paths.update((e,t) for e in eligible | set_edges for t in outgoing.get(e[2],())
                                  if (e,t)!=typed_set)
            for depth in ((2,8,32) if a.set_reader else (2,8)):
                guarded.append((f"set{depth}",dict(base_cfg,depth=depth,pair_walk=True,reuse_let=True,
                                set_edges=True,library=sorted(combined_paths)),"full"))
            if a.set_reader:
                from route_credit import continuation_edges
                learned = json.loads(a.set_reader.read_bytes())
                m = dict(learned,edges=continuation_edges(recipe,spec),expected_gain=True)
                for name,cfg,mode in guarded.copy():
                    if name in ("all_literal","set2","set8"):
                        guarded.append((name+"_reader",dict(cfg,route_reader=m),"full"))
        if a.depth_model:
            cfg = next(config for name,config,_ in guarded if name=="set8_reader")
            # Change only the chosen root family. Other roots retain depth eight.
            rid, = [i for i,r in enumerate(recipe["rules"]) if r["metadata"]["name"].startswith("(rewrite (SubTuple expr a b) (Concat")]
            model=dict(json.loads(a.depth_model.read_bytes()),rule=rid)
            for name,threshold in (("sub_shallow",1e20),("sub_learned",.5),("sub_deep",-1e20)):
                guarded.append((name,dict(cfg,depth=8,depth_reader=dict(model,threshold=threshold)),"full"))
            if a.depth_variants:
                for variant in ("clean_attention","mixed_max","mixed_attention","clean_anchored","mixed_anchored"):
                    weights=json.loads((a.depth_variants/(variant+".json")).read_bytes())
                    guarded.append(("sub_"+variant,dict(cfg,depth=8,depth_reader=dict(weights,rule=rid)),"full"))
                    if variant in ("mixed_max","mixed_anchored"):
                        guarded.append(("sub_"+variant+"_expected",dict(cfg,depth=8,
                                         depth_reader=dict(weights,rule=rid,threshold=0.)),"full"))
        if a.row_guards:
            from guard_catalog import extend
            for name,cfg,mode in guarded.copy():
                if name in ("sub_deep","sub_learned"):
                    updated=extend(recipe,cfg,typed_set)
                    guarded.append((name+"_guard",updated,mode))
                    if name=="sub_learned":
                        guarded.append(("sub_expected_guard",dict(updated,depth_reader=dict(
                            cfg["depth_reader"],threshold=0.)),mode))
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
                if a.parent_projection and name not in ("leaf","sub_expected_guard"):
                    continue
                if a.walk and not (a.depth_model and name.startswith("sub_")) and name not in ("leaf","all_literal","all_literal_reader") and not name.startswith(("walk","set")):
                    continue
                if a.set_edges and not (a.depth_model and name.startswith("sub_")) and name not in ("leaf","all_literal","walk2_reuse1","set2","set8","set32","set2_reader","set8_reader","all_literal_reader"):
                    continue
                if a.depth_model and name not in ("leaf","set8_reader") and not name.startswith("sub_"):
                    continue
                if a.row_guards and name not in ("leaf","set8_reader","sub_deep","sub_learned","sub_deep_guard","sub_learned_guard","sub_expected_guard"):
                    continue
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
                if a.walk and name != "leaf":
                    from walk_credit import validate
                    results[name].update(validate(data,cfg))
                if cfg.get("row_guards"):
                    results[name]["guards"]=data["strict_named"]["row_guard_checks"]
                    if a.parent_projection:
                        from parent_projection import projection_profile
                        results[name]["projection"] = projection_profile(data)
                    commits=Counter(
                        link[2][-1][-1] for link in data["strict_named"]["signed_commits"]
                        if len(recipe["rules"][link[2][-1][-1]]["query"])>1)
                    results[name]["guarded_commits"]=dict(commits)
                if "depth_reader" in cfg:
                    choices,runs=data["strict_named"]["depth_choices"]
                    target=cfg["depth_reader"]["rule"]
                    source={row[2] for row in data["root_recipe"]["commits"] if row[3]==target}
                    internal={link[0] for link in data["strict_named"]["signed_commits"]}
                    external=source-internal
                    if sum(choices)!=len(external):
                        raise ValueError((case,name,"unaccounted depth subject",len(external),choices))
                    if (not runs and external) or choices[0] or (name=="sub_shallow" and choices[2]) or (name=="sub_deep" and choices[1]):
                        raise ValueError((case,name,"missing or unexpected depth decision",choices,runs))
                    results[name].update(depth_choices=choices,depth_runs=runs,depth_source=len(source),depth_internal=len(source)-len(external))
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
        if a.depth_model and not a.parent_projection:
            if results["sub_deep"]["paid"] != results["set8_reader"]["paid"]:
                raise ValueError((case,"forcing eight hops changed the fixed-depth control"))
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
    p.add_argument("--walk",action="store_true")
    p.add_argument("--set-edges",action="store_true")
    p.add_argument("--set-reader",type=Path)
    p.add_argument("--depth-model",type=Path)
    p.add_argument("--depth-variants",type=Path)
    p.add_argument("--row-guards",action="store_true")
    p.add_argument("--parent-projection", action="store_true")
    args=p.parse_args()
    if args.parent_projection and not args.row_guards:
        p.error("--parent-projection evaluates the guarded policy")
    if args.row_guards and not args.depth_model:
        p.error("--row-guards compares the frozen depth policy")
    if args.depth_variants and not args.depth_model:
        p.error("--depth-variants needs the clean --depth-model control")
    if args.depth_model and not args.set_reader:
        p.error("--depth-model compares against the frozen --set-reader control")
    args.set_edges |= bool(args.set_reader)
    args.walk |= args.set_edges
    if args.walk and (args.live or args.recurrent or args.expected):
        p.error("--walk uses fixed route admission")
    args.recurrent |= args.expected
    args.live |= args.recurrent
    args.literal |= args.live or args.walk
    main(args)

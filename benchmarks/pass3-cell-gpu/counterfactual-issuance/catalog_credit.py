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
    if a.source_delta:
        from source_delta import train as train_delta
        report["source_delta_training"]=train_delta(a.pair_device)
    if a.pair_owner:
        from pair_owner import action_table, fit as fit_pair, generated, replay, wiring
        policies = {name:fit_pair(9203,count,clean,width,steps,a.pair_device)
                    for name,count,clean,width,steps in (
                        ("clean",2048,True,8,240),("small_data",32,False,8,240),
                        ("short",2048,False,8,4),("mixed",2048,False,8,240),
                        ("wide",2048,False,32,240))}
        x, y = generated(9317,4096,False)
        report["pair_training"] = dict(device=a.pair_device, test_rows=len(y),
            correct={k:int(((m(x).flatten()>=0)==y.bool()).sum()) for k,m in policies.items()})
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
            if a.ept:
                from ept import ledger_digest,score
                exact_events=run(dict(baseline=True,audit=True,ept=True))
                if any(exact_events.get(k)!=exact[k] for k in ("state_sha","runs","schedule","rhs","writes","resumes")):
                    raise ValueError(("invalid exact EPT reference",exact_events.get("source_error")))
                reference=ledger_digest(exact_events)
                del exact_events
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
                request = matrix["cfg"](req,cfg,True)
                if a.pair_owner and name=="sub_expected_guard":
                    target, column, pairs = wiring(recipe,a.pair_tables)
                    trace_rules = set(pairs)
                    if a.history_ports:
                        history_targets = {rid for rid,r in enumerate(recipe["rules"])
                                   if len(r["query"]) == 2 and all(
                                       atom["call"].get("table") in ctors for atom in r["query"])}
                        tables = {a["call"]["table"] for rid in history_targets for a in recipe["rules"][rid]["query"]}
                        trace_rules.update(rid for rid,r in enumerate(recipe["rules"]) if any(
                            op.get("kind") == "construct" and op["call"]["table"] in tables for op in r["effects"]))
                    request["pair_trace_rules"] = sorted(trace_rules)
                    request["pair_policy"] = dict(ambiguous_control=a.pair_ambiguous,takeover=a.pair_takeover,column=column,target=target, wiring=pairs, actions=list(action_table(policies["mixed"]).values()))
                if a.pair_takeover and name=="sub_expected_guard":
                    shadow=run(dict(request,pair_policy=dict(request["pair_policy"],takeover=False)))
                    shadow_lanes=Counter(map(tuple,shadow["root_recipe"]["pair_external"]))
                    shadow_paid=study["packets"](shadow)
                    del shadow
                if a.source_delta and name=="sub_expected_guard":
                    size_rule,=[i for i,r in enumerate(recipe["rules"])
                             if r["metadata"]["name"].startswith("(rule ((= expr (Get tup i))")
                             and r["effects"][-1].get("call",{}).get("table")=="Expr-size"]
                    request["size_reader"]=dict(local=a.source_delta in ("local","distinct"),tests=report["source_delta_training"]["tests"]["distinct" if a.source_delta=="distinct" else "ties"]["actions"],size_rule=size_rule,filter=True,only_size=a.source_delta=="size",
                        actions=report["source_delta_training"]["arms"]["mixed"]["actions"])
                if a.history_ports and name=="sub_expected_guard":request["history_ports"]=True
                if a.ept:request["ept"]=True
                data = run(request)
                counts, ledger = matrix["summarize"](data,exact,bool(mode))
                if baseline is None:
                    baseline = counts
                if a.pair_takeover:
                    commits=data["root_recipe"]["commits"]
                    if name=="leaf":
                        reference_serials={r[0]:r[2] for r in commits}
                    # Compare full commit and allocation records after translating only
                    # private packet serials to the same source ordinal in the leaf arm.
                    counts["commits"]=matrix["digest"]([[*r[:2],reference_serials[r[0]],*r[3:]] for r in commits])
                    serials={r[2]:reference_serials[r[0]] for r in commits}
                    counts["physical"]=matrix["digest"]([[*r[:5],serials[r[5]]] for r in data["root_recipe"]["fresh"]])
                for key in matrix["FIXED"]:
                    if counts[key] != baseline[key]:
                        raise ValueError((case,name,key))
                paid = study["packets"](data)
                saved = baseline["packets"] - paid
                pair_children = data["root_recipe"].get("pair_children") or []
                if pair_children:
                    from pair_owner import validate_children
                    validate_children(data,target,pair_children,ledger[0])
                delta_counts=data.get("size_reader") or {}
                skipped=sum(c[0]+c[1] for c in delta_counts.values())
                if skipped!=data.get("size_omission_checks",0):
                    raise ValueError("source omissions lack independent rejection receipts")
                displaced_rejects=0
                if a.pair_takeover and name=="sub_expected_guard":
                    from pair_owner import compare_residual
                    displaced_rejects=compare_residual(data,shadow_lanes)
                    if shadow_paid-paid != len(pair_children)+displaced_rejects+skipped:
                        raise ValueError((case,"unexplained difference from guarded shadow",shadow_paid,paid,len(pair_children),displaced_rejects))
                if saved != len(ledger[0])+len(pair_children)+displaced_rejects+skipped or paid != counts["packets"]:
                    raise ValueError((case,name,"unattributed packet"))
                results[name] = dict(paid=paid, saved=saved, visible=counts["visible"], fept=counts["fept"],
                                     terminal=counts["set_internal"], checks=counts["checks"],
                                     paths=len(cfg.get("library",[])), state_sha=counts["state_sha"])
                if delta_counts:
                    votes=data["size_predictions"]
                    if votes:
                        prediction=dict(votes)
                        writes={n for run in data["ept"] for kind,n,*_ in run if kind==1}
                        confusion=Counter()
                        for n,_,rid,_,_,_,_,_,ticket,*_ in data["single"]["committed"]:
                            if rid==size_rule:
                                if ticket not in prediction:raise ValueError("missing size forecast")
                                confusion[int(prediction[ticket]),int(n in writes)]+=1
                        results[name]["size_forecast"]=[[confusion[a,b] for b in range(2)] for a in range(2)]
                    results[name]["source_delta"]=delta_counts
                    results[name]["source_delta_omitted"]=skipped
                if a.ept:results[name]["effective_ops"]=score(data,recipe,paid,reference)
                if a.walk and name != "leaf":
                    from walk_credit import validate
                    results[name].update(validate(data,cfg))
                if cfg.get("row_guards"):
                    results[name]["guards"]=data["strict_named"]["row_guard_checks"]
                    if a.pair_owner:
                        axioms={i for i,r in enumerate(recipe["rules"]) if not r["query"] and all(slot["definition"]!="query" for slot in r["slots"])}
                        results[name]["pair_issuance"] = replay(data,target,pairs,policies,a.pair_takeover,axioms)
                        results[name]["pair_displaced_extra_lanes"] = displaced_rejects
                        results[name]["pair_committed"] = len(pair_children)
                        results[name]["pair_checks"] = data["root_recipe"]["pair_checks"]
                        if a.history_ports:
                            from parent_projection import prior_port_coverage
                            results[name]["prior_ports"] = prior_port_coverage(data,history_targets)
                            from history_reader import study as history_study
                            results[name]["history_reader"] = history_study(data,recipe)
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
    p.add_argument("--pair-owner",action="store_true")
    p.add_argument("--pair-device",choices=("mps","cpu"),default="mps")
    p.add_argument("--pair-takeover",action="store_true")
    p.add_argument("--pair-ambiguous",action="store_true")
    p.add_argument("--pair-tables",nargs=2,default=("PotentialExtractedExpr","TCPair"))
    p.add_argument("--history-ports", action="store_true")
    p.add_argument("--ept",action="store_true")
    p.add_argument("--source-delta",choices=("size","all","local","distinct"))
    args=p.parse_args()
    if args.source_delta:
        args.pair_takeover=True
        args.ept=True
    args.pair_takeover |= args.pair_ambiguous
    args.pair_owner |= args.pair_takeover
    args.pair_owner |= args.history_ports
    args.parent_projection |= args.pair_owner
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

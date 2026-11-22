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
        baseline = None
        results = {}
        with study["src"].base.session(a.native,program,plans) as run:
            for name, cfg, mode in (("leaf",catalog["leaf"],None),("original",spec,"greedy"),
                                    ("union",catalog["union"],"greedy"),("expanded",combined,"greedy"),
                                    ("wide_let_only",let_only,None),("wide",wide,"greedy"),("fixed_full",wide,"full")):
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
                print(case,name,paid,saved,flush=True)
        report["cases"][case] = results
        (a.out/"catalog-credit.json").write_text(json.dumps(report,indent=2)+"\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("exp","native","training","out"):
        p.add_argument(key,type=Path)
    p.add_argument("--cases",nargs="+",default=["sum-bits","3mm"])
    main(p.parse_args())

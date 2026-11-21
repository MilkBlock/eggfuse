"""Run the signed cross-Run and within-RHS portfolios on the original Pass 3 schedule."""
import argparse
import json
from pathlib import Path
from runpy import run_path
from statistics import median
from time import perf_counter
from policy import export_policy
from library import catalog, atomic_write

HERE = Path(__file__).resolve().parent
matrix = run_path(str(HERE.parent/"ripsat-publication-matrix/study.py"))
bridge = run_path(str(HERE.parent/"explicit-parent-cell-composition/ripsat_bridge.py"))


def work(a):
    a.out.mkdir(parents=True, exist_ok=False)
    donors = {name:a.exp/"compact-holdouts-20261121-v1"/(name+"-1703")/"program.json"
              for name in ("dot-product","jacobi-1d")}
    checkpoint = json.loads(a.checkpoint.read_bytes())
    if checkpoint.get("schema") != "eggfuse-fragment-ridge/v1":
        raise ValueError("expected a frozen PyTorch training export")
    result = dict(checkpoint=checkpoint, inference_device="single-threaded Rust CPU", cases={})
    for case in ("sum-bits","3mm"):
        program,plans,req = matrix["src"].config(a,case)
        lib = catalog(donors.values(),program,a.prover.resolve(),5,4)
        # Never consume a cache without relinking and checking native closure.
        archived = json.loads((a.inputs/(case+"-fragments.json")).read_bytes())
        if json.loads(json.dumps(lib)) != archived:
            raise ValueError("constructor fragment library failed independent reconstruction")
        signed = bridge["load_checked"](a.inputs/(case+".json"),program,trust_index=a.inputs/"archive/trust.json")
        specs,_ = matrix["libraries"](a.exp,program,case)
        req["source_sha256"] = lib["target_sha256"]
        configs = {k:dict(v) for k,v in specs.items() if k in matrix["METHODS"]}
        for name in ("ripsat","union"):
            configs[name]["library"] = sorted({tuple(map(tuple,p)) for p in
                   configs[name]["library"]+signed["strict_named"]["library"]})
        policies = {"union_size":export_policy(lib,checkpoint,largest=True),"union_ridge":export_policy(lib,checkpoint)}
        configs.update({k:configs["union"] for k in policies})
        rows,settings = {},{}
        with matrix["src"].base.session(a.exp/"compact-vanilla-20261121/vanilla-audit",program) as run:
            gold = run({"audit":True})
        with matrix["src"].base.session(a.native,program,plans) as run:
            exact = run({"baseline":True})
            assert "source_error" not in exact and exact["state_sha"]==gold["state_sha"] and exact["runs"]==gold["runs"]
            exact_ms, exact_wall = [], []
            for name,spec in configs.items():
                cfg = dict(matrix["cfg"](req,spec,True),rhs_fragments=policies.get(name))
                v = run(cfg)
                row,_ = matrix["summarize"](v,gold,name not in ("leaf","trace"))
                matched = matrix["src"].base.summarize(v,gold)
                row["coverage"] = {k:matched[k] for k in ("neural_rhs","source_pass_rhs","fresh","direct_cells",
                    "rejected","applied","root_allocated","wire_bytes")}
                row["coverage"]["residual_rhs"] = row["rhs"]-matched["neural_rhs"]
                row["coverage"]["duplicates_in_committed_ordinals"] = 0  # summarize checks disjoint unique ordinals
                row["coverage"]["multi_residual_enabled"] = req["multi_residual"]
                row["coverage"]["single_residual_enabled"] = json.loads(Path(req["single_config"]).read_bytes())["residual"]
                row["coverage"]["named_port_probes"] = (v["strict_named"] or {}).get("counts",{})
                ledger = v["rhs_fragments"]
                row["fragment_shapes"] = len({r[1] for r in ledger if r[2]})
                row["fragment_sites_issued"] = sum(r[2] for r in ledger)
                row["fragment_roots_accepted"] = sum(r[3] for r in ledger)
                row["fragment_ops"] = sum(r[4] for r in ledger)
                row["fragment_completions"] = sum(r[5] for r in ledger)
                writes = {(serial,op):shape for shape,records in v.get("rhs_fragment_writes",[]) for serial,op in records}
                assert len(writes)==row["fragment_ops"]
                final = {fid for fid,_,hidden in v["constructor_births"]["endpoint"] if not hidden}
                credit = {}
                for fid,_,_,ctor,serial,_,_,flags in v["constructor_births"]["rows"]:
                    shape = writes.get((serial,fid & 0xffffffff))
                    if shape is not None and ctor and flags&1 and not flags&2 and fid in final:
                        credit.setdefault(shape,set()).add(fid)
                row["fragment_final_origins"] = {k:len(v) for k,v in sorted(credit.items())}
                row["fragment_ledger"] = ledger
                rows[name] = row
                assert all(row[k]==rows["leaf"][k] for k in matrix["FIXED"]), (case,name)
                assert rows["leaf"]["packets"]-row["packets"]==row["internal"]
                if name in policies:
                    assert row["fragment_ops"] and row["packets"]==rows["union"]["packets"]
                settings[name] = dict(matrix["cfg"](req,spec),rhs_fragments=policies.get(name))
                print(case,name,row["packets"],row["fept"],row["fragment_ops"],flush=True)
            for lap in range(5):
                started=perf_counter()
                baseline=run({"baseline":True})
                assert baseline["state_sha"]==gold["state_sha"] and baseline["runs"]==gold["runs"]
                if lap:
                    exact_ms.append(baseline["ms"])
                    exact_wall.append(1000*(perf_counter()-started))
                arms=list(settings)
                for name in arms[lap%len(arms):]+arms[:lap%len(arms)]:
                    started=perf_counter()
                    v=run(settings[name])
                    wall_ms=1000*(perf_counter()-started)
                    row=rows[name]
                    assert v["state_sha"]==row["state_sha"] and v["runs"]==row["runs"]
                    assert v["root_recipe"]["emitted"]==row["emitted"] and v["rhs_fragments"]==row["fragment_ledger"]
                    if lap:
                        row.setdefault("ms",[]).append(v["ms"])
                        row.setdefault("resident_request_ms",[]).append(wall_ms)
        for row in rows.values(): row["median_ms"]=median(row["ms"])
        result["cases"][case]=dict(exact_cpu_ms=exact_ms,exact_cpu_resident_request_ms=exact_wall,exact_cpu_median_ms=median(exact_ms),templates=len(lib["entries"]),target_sha256=lib["target_sha256"],arms=rows)
        atomic_write(a.out/"results.json",result)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ("exp","native","prover","inputs","out"):
        p.add_argument(arg,type=Path)
    p.add_argument("--checkpoint", required=True, type=Path)
    work(p.parse_args())

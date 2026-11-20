"""Time typed page validation and diagnostic hashing on a complete source execution."""
import argparse
import importlib.util
import json
from contextlib import ExitStack
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("paired_pass", HERE.parent / "pair-source-frontier/study.py")
paired = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paired)
MODES = {"off": 0, "hash": 1, "borrow": 2, "atoms": 6, "typed": 10, "headers": 18, "all": 31}
SAME = ("raw","wire_hash","emitted","applied","physical","commits","multi","children","cells",
        "single_winners","multi_winners","root_parents","root_ids","nested_ids","direct_cells","root_allocated")


def run(args):
    args.out.mkdir(parents=True, exist_ok=False)
    export = {}
    vanilla_dir = args.exp / "compact-vanilla-20261121"
    for case in args.cases:
        program, plans, req = paired.common.config(args, case)
        main = dict(req, header_mode=3, derived_ports=dict(mode=1,cache=True), lazy_equations=4)
        with paired.base.session(vanilla_dir / "vanilla-audit",program) as src:
            gold = src(dict(audit=True))
        with ExitStack() as stack:
            vanilla = stack.enter_context(paired.base.session(vanilla_dir / "vanilla",program))
            infer = stack.enter_context(paired.base.session(args.native,program,plans))
            rows = {"vanilla":dict(runs=gold["runs"],rhs=gold["rhs_count"],ms=[])}
            for name,bits in MODES.items():
                out = infer(dict(main,lean_root=bits,audit=True))
                result = paired.base.summarize(out,gold)
                for key in ("rows","work"):
                    del result[key]
                result["counts"] = out["multi"]["counts"]
                result["audit_lean"] = out["root_recipe"]["lean"]
                result["sealed"] = out["root_recipe"]["sealed"]
                assert result["audit_lean"]["raw_omitted"]==0
                if name!="off":
                    for key in SAME:
                        assert result[key]==rows["off"][key],(case,name,key)
                rows[name]=result
                del out

            if case=="sum-bits":
                for fault in (1,2,3):
                    out=infer(dict(main,lean_root=31,multi_root_fault=fault))
                    assert out.get("source_error") and out["runs"]<gold["runs"],out.get("source_error")
                    rows["all"].setdefault("faults",{})[str(fault)]=[out["runs"],out["source_error"]]

                for control in ("wrong-port","wrong-template","withhold"):
                    root=json.loads(Path(main["root_config"]).read_bytes())
                    root["control"]=control
                    filename=args.out/("invalid-"+control+".json")
                    filename.write_text(json.dumps(root))
                    previous=None
                    for mode in (0,31):
                        out=infer(dict(main,root_config=str(filename),lean_root=mode))
                        assert out.get("source_error") and out["runs"]<gold["runs"],(control,out.get("source_error"))
                        failed=[out["runs"],out["source_error"]]
                        if previous is not None:
                            assert failed==previous,(control,failed,previous)
                        previous=failed
                    rows["all"]["faults"][control]=previous

            names=list(rows)
            for i in range(1+args.repeats):
                pos=i%len(names)
                order=names[pos:]+names[:pos]
                for name in order if i%2 else reversed(order):
                    out=vanilla({}) if name=="vanilla" else infer(dict(main,lean_root=MODES[name],audit=False))
                    row=rows[name]
                    assert out["state_sha"]==gold["state_sha"] and out["runs"]==gold["runs"]
                    if name!="vanilla":
                        root=out["root_recipe"]
                        for key in ("emitted","sealed","applied"):
                            assert root[key]==row[key]
                        assert root["allocated"]==row["root_allocated"] and root["rejected"]==row["rejected"]
                        omitted=bool(MODES[name]&1)
                        assert root["lean"]["raw_omitted"]==(sum(root["emitted"]) if omitted else 0)
                        assert root["raw_hash"]==(None if omitted else rows["off"]["raw"])
                        prod=root["lean"]
                        assert prod["archived_refs"]==0
                        for key in ("single_binds","multi_binds","projected_values","produced_refs","skipped_atom_checks","typed_rows","wire_bytes_avoided","fused_header_reads"):
                            assert prod[key]==row["audit_lean"][key]
                        row["production"]=prod
                    if i: row["ms"].append(out["ms"])
            for row in rows.values(): row["median_ms"]=median(row["ms"])
            print(case,[(n,round(r["median_ms"],2)) for n,r in rows.items()],flush=True)
        export[case]=rows
        (args.out/"results.json").write_text(json.dumps(export,indent=1)+"\n")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("exp","native","out"):
        p.add_argument(name,type=Path)
    p.add_argument("--cases",nargs="+",default=["sum-bits","3mm"])
    p.add_argument("--seed",type=int,default=1703)
    p.add_argument("--repeats",type=int,default=4)
    run(p.parse_args())

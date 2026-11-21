"""Ablate a move-only multi-parent root on the complete verified/filtered/packed source path."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
from runpy import run_path
from statistics import median
from time import perf_counter

HERE=Path(__file__).resolve().parent
wave=run_path(str(HERE.parent/"verified-wave-execution/study.py"))
source=wave["source"]
ENDPOINTS=("rhs","raw","multi","wire_hash","commits","physical","source_pass_rhs","root_ids","root_parents",
           "nested_ids","children","state_sha","single_winners","multi_winners","cells","direct_cells")


def settings(req,a):
    packed=wave["settings"](req,a)["packed"]
    return {"directory":packed,"instance":dict(packed,instance_claim=1)}


def counters(v):
    return v["multi"]["instance_claims"]


def checked(v,gold):
    row=source.base.summarize(v,gold)
    del row["rows"],row["work"]
    assert row["aligned"] and all(row["checks"].values())
    row.update(claims=counters(v),queue=v["single"]["packed"],
               scores=v["single"]["adaptive_rows"]["decision_digest"],events=v["multi"]["wave"])
    assert row["queue"]["lanes"]>0 and row["rhs"]==row["neural_rhs"]
    row.update(ms=[],wall_ms=[],phase_ms=[])
    return row


def measure(a):
    a.out.mkdir(parents=True,exist_ok=False)
    results={}
    original=a.exp/"compact-vanilla-20261121"
    for case in a.cases:
        program,plans,req=source.common.config(a,case)
        arms=settings(req,a)
        with source.base.session(original/"vanilla-audit",program) as run:gold=run({"audit":True})
        rows={"vanilla":{"rhs":gold["rhs_count"],"runs":gold["runs"],"ms":[],"wall_ms":[]}}
        with ExitStack() as stack:
            infer=stack.enter_context(source.base.session(a.native,program,plans))
            vanilla=stack.enter_context(source.base.session(original/"vanilla",program))
            for name,cfg in arms.items():
                v=infer(dict(cfg,audit=True)); assert "source_error" not in v
                rows[name]=checked(v,gold);del v
            ref=rows["directory"];opt=rows["instance"]
            for k in (*ENDPOINTS,"queue","scores","events"):assert ref[k]==opt[k],(case,k)
            a_count=opt["claims"]["counts"]
            assert a_count["attached"]==opt["claims"]["tickets"]==ref["claims"]["tickets"]
            assert a_count["transferred"]==a_count["archived_comparisons"]>0
            bad=infer(dict(arms["instance"],instance_claim=2))
            assert "instance claim disagrees" in bad.get("source_error","") and bad["runs"]<gold["runs"]
            rows["corruption"]={"error":bad["source_error"],"completed_runs":bad["runs"]}
            names=["vanilla","directory","instance"]
            for sample in range(1+a.repeats):
                seq=names[sample%3:]+names[:sample%3]
                for name in seq if sample%2 else reversed(seq):
                    start=perf_counter();v=vanilla({}) if name=="vanilla" else infer(dict(arms[name],audit=False))
                    wall=1000*(perf_counter()-start)
                    assert v["runs"]==gold["runs"] and v["state_sha"]==gold["state_sha"]
                    if name!="vanilla":
                        assert v["root_recipe"]["allocated"]==rows[name]["root_allocated"]
                        assert v["root_recipe"]["applied"]==rows[name]["rhs"]
                        assert v["multi"]["total_rhs"]==gold["rhs_count"]
                        c=counters(v)
                        assert c["counts"]["archived_comparisons"]==0
                        if name=="instance":
                            assert c["tickets"]==c["directory_bytes"]==0
                            assert c["counts"]["attached"]==a_count["attached"] and c["counts"]["transferred"]==a_count["transferred"]
                        else:assert c["tickets"]==a_count["attached"] and c["directory_bytes"]>0
                        rows[name]["normal_claims"]=c
                        if sample:rows[name]["phase_ms"].append(v["phases_ms"])
                    if sample:
                        rows[name]["ms"].append(v["ms"]);rows[name]["wall_ms"].append(wall)
            for name in names:
                rows[name]["median_ms"]=median(rows[name]["ms"])
                rows[name]["median_wall_ms"]=median(rows[name]["wall_ms"])
        results[case]=rows;(a.out/"results.json").write_text(json.dumps(results,indent=1)+"\n")
        print(case,[(name,round(rows[name]["median_ms"],2),round(rows[name]["median_wall_ms"],2)) for name in names],a_count,flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for key in ("exp","native","out"):p.add_argument(key,type=Path)
    p.add_argument("--cases",nargs="+",default=["conjugate-gradient","3mm"])
    p.add_argument("--repeats",type=int,default=6)
    a=p.parse_args();a.seed=1703;a.cap=8192
    a.policy=json.loads((HERE.parent/"speculative-allocation-policy/policy.json").read_bytes())
    a.fraction=json.loads((HERE.parent/"wave-demand-policy/policy.json").read_bytes())["models"]["fraction"]
    measure(a)

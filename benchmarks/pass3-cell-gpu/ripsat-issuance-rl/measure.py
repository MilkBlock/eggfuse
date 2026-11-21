"""Paired CPU timings and fresh-process RSS for the frozen issuing head."""
import argparse
import json
from pathlib import Path
from runpy import run_path
from statistics import median
from time import perf_counter

HERE=Path(__file__).resolve().parent
study=run_path(str(HERE/"study.py"))
matrix=study["matrix"]
rss=run_path(str(HERE.parent/"ripsat-publication-matrix/rss.py"))


def main(a):
    a.out.mkdir(parents=True,exist_ok=False)
    weights=json.loads(a.checkpoint.read_bytes())["weights"]
    audited=json.loads(a.evaluation.read_bytes())
    out={}
    for case in ("sum-bits","3mm"):
        program,plans,req,spec=study["setup"](a,case)
        levels=json.loads(rss["cal_file"].read_bytes())[case]["thresholds_kib"]["0.9"]
        configs={};want={};rows={}
        with study["src"].base.session(a.native,program,plans) as run:
            ref=run({"baseline":True,"audit":True})
            for name,mode in [("leaf","leaf"),("learned","greedy"),("full","full"),("stale","greedy")]:
                variant=dict(spec,issuance_actor=dict(mode=mode,seed=0,weights=weights))
                if name=="stale":variant["set_fault"]="stale"
                cfg=matrix["cfg"](req,variant)
                v=run(matrix["cfg"](req,variant,True))
                for k in ("rhs","writes","resumes","schedule","runs","state_sha"):
                    assert v[k]==ref[k],(case,k)
                counts=v["strict_named"]
                count=len(counts["signed_commits"])
                packets=study["packets"](v)
                row=dict(packets=packets,child_proposals=sum(int(c["selected"]) for c in v["merge_child"]["issued"]),
                    signed=count,terminal=counts["set_publication"]["confirmed"],root_rejections=v["root_recipe"]["rejected"],
                    receiver_counts=counts["counts"],exact_rhs=len(v["root_recipe"]["commits"])-len(v["single"]["committed"])-len(v["multi"]["tickets"]))
                assert row["exact_rhs"]==0
                if name=="stale":
                    assert row["terminal"]==0 and packets-rows["learned"]["packets"]==rows["learned"]["terminal"]
                else:
                    assert packets==audited[case][name]["packets"]
                rows[name]=row;configs[name]=cfg
                want[name]=dict(runs=v["runs"],state_sha=v["state_sha"],emitted=v["root_recipe"]["emitted"],internal=count,set_internal=row["terminal"])
            timed=["exact","leaf","learned","full"]
            rows["exact"]={}
            for lap in range(5):
                for name in timed[lap%4:]+timed[:lap%4]:
                    start=perf_counter()
                    v=run({"baseline":True} if name=="exact" else configs[name])
                    wall=(perf_counter()-start)*1000
                    assert v["state_sha"]==ref["state_sha"] and v["runs"]==ref["runs"]
                    if lap:
                        rows[name].setdefault("native_ms",[]).append(v["ms"])
                        rows[name].setdefault("request_ms",[]).append(wall)
            for n in timed:
                rows[n]["median_native_ms"]=median(rows[n]["native_ms"])
                rows[n]["median_request_ms"]=median(rows[n]["request_ms"])
        for lap in range(4):
            arms=["leaf","learned","full"]
            for n in arms[lap%3:]+arms[:lap%3]:
                pair={s:rss["one"](a.native,program,plans,configs[n],s,want[n]) for s in
                      ((True,False) if (lap+arms.index(n))%2 else (False,True))}
                trace=pair[True]["trace"]
                rows[n].setdefault("rss",[]).append(dict(increment=rss["crossing"](trace,trace[0][1]+levels[1]),
                    peak_kib=max(k for us,k in trace),control_ms=pair[False]["ms"]))
        out[case]=dict(growth_kib=levels[1],arms=rows)
        study["write"](a.out/"results.json",out)
        print(case,"timing and receipt controls passed",flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ("exp","native","out","checkpoint","evaluation"):parser.add_argument(key,type=Path)
    main(parser.parse_args())

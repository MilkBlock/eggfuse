"""Sample resident full-session execution of each exact portfolio in a fresh process."""
import argparse
import json
from pathlib import Path
from runpy import run_path
from statistics import median
from library import atomic_write, catalog
from policy import export_policy

HERE=Path(__file__).resolve().parent
driver=run_path(str(HERE/"study.py"))
bridge, matrix=driver["bridge"],driver["matrix"]
observer=run_path(str(HERE.parent/"ripsat-publication-matrix/rss.py"))
def run(a):
    a.out=a.output.parent
    a.out.mkdir(parents=True,exist_ok=True)
    study=json.loads(a.study.read_bytes())
    calibration=json.loads(observer["cal_file"].read_bytes())
    checkpoint=study["checkpoint"]
    data={}
    if set(study["cases"]) != {"sum-bits", "3mm"}:
        raise ValueError("both semantic runs must finish before RSS sampling")
    for case,source in study["cases"].items():
        rows=source["arms"]
        program,plans,req=matrix["src"].config(a,case)
        donors=[a.exp/"compact-holdouts-20261121-v1"/(n+"-1703")/"program.json" for n in ("dot-product","jacobi-1d")]
        library=catalog(donors,program,a.prover.resolve(),5,4)
        if json.loads(json.dumps(library)) != json.loads((a.inputs/(case+"-fragments.json")).read_bytes()):
            raise ValueError("unverified fragment library")
        strict=bridge["load_checked"](a.inputs/(case+".json"),program,trust_index=a.inputs/"archive/trust.json")
        spec,_=matrix["libraries"](a.exp,program,case)
        req["source_sha256"]=library["target_sha256"]
        for name in ("union","ripsat"):
            spec[name]["library"]=sorted({tuple(map(tuple,p)) for p in spec[name]["library"]+strict["strict_named"]["library"]})
        methods=["leaf","trace","ripsat","union","union_ridge"]
        policy=export_policy(library,checkpoint)
        cfg={n:matrix["cfg"](req,spec["union" if n=="union_ridge" else n]) for n in methods}
        cfg["union_ridge"]["rhs_fragments"]=policy
        traces={n:[] for n in methods}
        growth=calibration[case]["thresholds_kib"]["0.9"][1]
        for lap in range(4):
            for n in methods[lap:]+methods[:lap]:
                trials={flag:observer["one"](a.native,program,plans,cfg[n],flag,rows[n])
                        for flag in ((False,True) if (lap+methods.index(n))%2 else (True,False))}
                points=trials[True]["trace"]
                traces[n].append(dict(crossing=observer["crossing"](points,points[0][1]+growth),
                    peak_kib=max(rss for _,rss in points),sampled_ms=trials[True]["ms"],control_ms=trials[False]["ms"]))
            print(case,lap+1,flush=True)
        data[case]=dict(growth_kib=growth,arms={n:dict(trials=v,
            reached=sum(t["crossing"][0]=="reached" for t in v),
            crossing_us=median(t["crossing"][1] for t in v) if all(t["crossing"][0]=="reached" for t in v) else None,
            control_ms=median(t["control_ms"] for t in v)) for n,v in traces.items()})
        atomic_write(a.output,data)

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("exp","native","prover","inputs","study","output"):
        p.add_argument(name,type=Path)
    run(p.parse_args())

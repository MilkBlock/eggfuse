"""Measure fixed incremental and absolute OS RSS watermarks for strict source execution."""
import argparse
import json
from pathlib import Path
from runpy import run_path

HERE=Path(__file__).resolve().parent
driver=run_path(str(HERE/"study.py"));strict=driver["strict"]
run=run_path(str(HERE.parent/"verified-wave-rss/measure.py"))["run"]


def main(a):
    a.out.mkdir(parents=True,exist_ok=False)
    targets=json.loads((HERE.parent/"verified-wave-rss/results.json").read_bytes())
    audit=json.loads(a.audit.read_bytes())
    lib=json.loads(a.library.read_bytes())
    results={}
    for case,record in audit.items():
        prog,plans,req=strict.src.config(a,case)
        _,idx=strict.bake.base["schema_map"](prog)
        l1=strict.bake.relink(lib['1']['paths'],idx);l2=strict.bake.relink(lib['2']['paths'],idx)
        configs={"leaf":{"depth":0},"compiled1":{"depth":1},"compiled2":{"depth":2},
                 "baked1":{"depth":1,"library":l1},"baked2":{"depth":2,"library":l1+l2}}
        levels=targets[case]["thresholds_kib"]["0.9"]
        names=list(configs);arms={n:[] for n in names}
        for lap in range(3):
            for name in names[lap:]+names[:lap]:
                cfg=driver["filtered"](req,configs[name])
                v=run(a.native,(prog,plans),cfg,True);ref=record["arms"][name]
                assert v["runs"]==record["runs"] and v["state_sha"]==ref["state_sha"]
                trace=[p[:2] for p in v['trace']]
                start=trace[0][1];crossings={}
                for key,height in (("absolute",levels[0]),("increment",start+levels[1])):
                    t=next((t for t,b in trace if b>=height),None)
                    crossings[key]=["left" if start>=height else "unreached" if t is None else "reached",t]
                arms[name].append(dict(trace=trace,crossings=crossings,peak_kib=max(b for _,b in trace)))
        results[case]=dict(levels_kib=levels,arms=arms)
        (a.out/"rss.json").write_text(json.dumps(results,separators=(",",":"))+"\n")
        print(case, {k:[r["crossings"]["increment"] for r in v] for k,v in arms.items()},flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("exp","native","library","audit","out"):p.add_argument(k,type=Path)
    main(p.parse_args())

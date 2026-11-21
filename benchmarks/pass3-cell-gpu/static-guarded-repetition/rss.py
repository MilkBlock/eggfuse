"""Time to a fixed OS RSS increment for explicit-parent guarded depth treatments."""
import argparse
import json
from pathlib import Path
from runpy import run_path
HERE=Path(__file__).resolve().parent
study=run_path(str(HERE/"study.py"))
measure=run_path(str(HERE.parent/"verified-wave-rss/measure.py"))["run"]

def run(a):
    a.out.mkdir(parents=True,exist_ok=False)
    audit=json.loads(a.audit.read_bytes());limits=json.loads((HERE.parent/"verified-wave-rss/results.json").read_bytes())
    data={}
    for c,m in audit.items():
        prog,plan,req=study["src"].config(a,c)
        levels=limits[c]["thresholds_kib"]["0.9"]
        arms={n:[] for n in m}
        for lap in range(3):
            names=list(arms);names=names[lap:]+names[:lap]
            for n in names:
                cfg=study["guard"]["base"]["filtered"](req,dict(depth=int(n),partial=True,value_guards=True,repeat=True))
                v=measure(a.native,(prog,plan),cfg,True)
                assert v["state_sha"]==m[n]["source"] and v["runs"]==m[n]["runs"]
                pts=[p[:2] for p in v["trace"]]
                start=pts[0][1];cross={}
                for k,h in (("absolute",levels[0]),("increment",start+levels[1])):
                    t=next((t for t,b in pts if b>=h),None)
                    cross[k]=["unreached" if t is None else "left" if start>=h else "reached",t]
                arms[n].append(dict(trace=pts,crossings=cross,peak_kib=max(y for _,y in pts)))
        data[c]=dict(limits_kib=levels,arms=arms)
        (a.out/"rss.json").write_text(json.dumps(data,separators=(",",":"))+"\n")
        print(c,{k:[r["crossings"]["increment"] for r in v] for k,v in arms.items()},flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("exp","native","audit","out"):p.add_argument(k,type=Path)
    run(p.parse_args())

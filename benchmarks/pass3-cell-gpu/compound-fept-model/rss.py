"""Compare launches on predeclared common absolute and incremental resident-memory thresholds."""
import argparse
import json
from pathlib import Path
from runpy import run_path
from statistics import median

HERE=Path(__file__).resolve().parent
study=run_path(str(HERE/"study.py"))
measure=run_path(str(HERE.parent/"verified-wave-rss/measure.py"))["run"]
thresholds=json.loads((HERE.parent/"verified-wave-rss/results.json").read_bytes())


def sample(a):
    a.out.mkdir(parents=True,exist_ok=False)
    audit=json.loads(a.audit.read_bytes())
    out={}
    for case in audit:
        prog,plan,req=study["src"].common.config(a,case)
        modes=study["settings"](req,a,False)
        names=list(modes)
        limits=thresholds[case]["thresholds_kib"]["0.9"]
        groups={k:[] for k in names}
        for it in range(3):
            for k in names[it:]+names[:it]:
                r=measure(a.native,(prog,plan),modes[k],True)
                assert r["runs"]==audit[case]["runs"] and r["state_sha"]==audit[case]["arms"][k]["state_sha"]
                pts=[(p[0],p[1]) for p in r["trace"]]
                start=pts[0][1]
                crosses={}
                for name,level in (("absolute",limits[0]),("increment",start+limits[1])):
                    first=next((t for t,b in pts if b>=level),None)
                    crosses[name]=[("left" if start>=level else "reached") if first is not None else "unreached",first]
                groups[k].append(dict(trace=pts,peak_kib=max(b for t,b in pts),crossings=crosses))
        out[case]={"frozen_thresholds_kib":limits,"arms":groups}
        (a.out/"rss.json").write_text(json.dumps(out,separators=(",",":"))+"\n")
        print(case, {k:[r['crossings']['increment'] for r in v] for k,v in groups.items()},flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("exp","native","audit","out"):p.add_argument(k,type=Path)
    p.add_argument("--pool-study",action="store_true")
    a=p.parse_args();study["wide"]["joint"]["common"](a);sample(a)

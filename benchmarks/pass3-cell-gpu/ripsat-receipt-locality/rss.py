"""Measure time to pre-calibrated RSS levels in the final ownership/locality factorial."""
import argparse
import json
from pathlib import Path
from runpy import run_path
from statistics import median
HERE=Path(__file__).resolve().parent
joint=run_path(str(HERE/"combined.py"))
sample=run_path(str(HERE.parent/"ripsat-neural-bake/rss.py"))
thresholds=json.loads((HERE.parent/"verified-wave-rss/results.json").read_bytes())

def run(a):
    a.out.mkdir(parents=True,exist_ok=False);data={}
    signed=json.loads(a.audit.read_bytes())
    for case,rows in signed.items():
        p,plans,req=joint["src"].config(a,case)
        donors={n:a.exp/"compact-holdouts-20261121-v1"/(n+"-1703")/"program.json" for n in ("dot-product","jacobi-1d")}
        m=joint["mat"]
        cert=m["authorizer"]["load_checked"](m["AUTH"]/(case+".json"),HERE.parent/"ripsat-donor-evidence/evidence.json",donors,p)
        levels=thresholds[case]["thresholds_kib"]["0.9"]
        groups={name:[] for name in rows}
        for lap in range(3):
            arms=joint["ARMS"];order=arms[lap:]+arms[:lap]
            for name,higher,index in order:
                cfg=joint["base"]["settings"](req,cert,"higher" if higher else "direct")
                cfg["strict_named"]["receipt_scan"]=index
                row=rows[name]
                # Use the exact measurement ABI of the final four-arm RipSat study.
                expect={"source":row["state_sha"],"emitted":row["emitted"],"runs":row["runs"],
                        "internal":row["internal"],"audit_score_inputs":0}
                x=sample["measure"](a.native,(p,plans),cfg,True,expect)
                ts=x["trace"]; start=ts[0][1]
                x["peak_kib"]=max(v for t,v in ts)
                x["crossings"]={k:sample["crossing"](ts,h) for k,h in (("absolute",levels[0]),("increment",start+levels[1]))}
                groups[name].append(x)
        data[case]=dict(levels_kib=levels,arms=groups)
        (a.out/"rss.json").write_text(json.dumps(data,separators=(",",":"))+"\n")
        print(case,{n:[x["crossings"]["increment"] for x in v] for n,v in groups.items()},flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("exp","native","audit","out"):p.add_argument(k,type=Path)
    run(p.parse_args())

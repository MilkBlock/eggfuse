"""Sample macOS resident memory only during native inference, on three fresh processes per arm."""
import argparse,json
from pathlib import Path
from runpy import run_path
from statistics import median
HERE=Path(__file__).resolve().parent
study=run_path(str(HERE/"study.py"))
measure=run_path(str(HERE.parent/"verified-wave-rss/measure.py"))
analysis=run_path(str(HERE.parent/"verified-wave-rss/analyze.py"))


def sample(a):
    a.out.mkdir(parents=True,exist_ok=True);audits=json.loads(a.audit.read_bytes());results={}
    for case,case_audit in audits.items():
        program,plan,req=study["src"].common.config(a,case)
        all_arms=study["settings"](req,a,False);arms={k:all_arms[k] for k in case_audit["arms"]};gold=case_audit["arms"]["packed"]
        def capture(name):
            r=measure["run"](a.native,(program,plan),arms[name],True)
            assert r["state_sha"]==gold["state_sha"] and r["runs"]==case_audit["runs"]
            return r
        calibration=[capture("packed") for _ in range(3)]
        start=int(median(v["trace"][0][1] for v in calibration))
        rise=int(median(max(p[1] for p in v["trace"])-v["trace"][0][1] for v in calibration))
        levels={str(f):start+round(f*rise) for f in (.5,.9)}
        groups={m:[] for m in arms};names=list(arms)
        for lap in range(3):
            seq=names[lap%len(names):]+names[:lap%len(names)]
            for m in seq if lap%2 else reversed(seq):
                x=capture(m);t=x.pop("trace")
                gaps=[b[0]-a[0] for a,b in zip(t,t[1:])]
                assert min(gaps)>0 and t[0][0]==0 and t[-1][0]==x["interval_us"]
                x.update(start_kib=t[0][1],peak_kib=max(z[1] for z in t),max_gap_us=max(gaps),
                         crossings={f:analysis["first"](t,h) for f,h in levels.items()},
                         trace_delta_us_kib=[t[0][:2]]+[[y-x for x,y in zip(a[:2],b[:2])] for a,b in zip(t,t[1:])])
                groups[m].append(x)
        results[case]={"calibration":[{"start_kib":v["trace"][0][1],"peak_kib":max(x[1] for x in v["trace"])} for v in calibration],
               "levels_kib":levels,"arms":groups}
        (a.out/"rss.json").write_text(json.dumps(results,separators=(",",":"))+"\n")
        print(case,{m:[round(x["peak_kib"]/1024,1) for x in vs] for m,vs in groups.items()},flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("exp","native","audit","out"):p.add_argument(k,type=Path)
    p.add_argument("--single-policy",type=Path);p.add_argument("--gate-model",default="reward-0")
    a=p.parse_args();study["common"](a);sample(a)

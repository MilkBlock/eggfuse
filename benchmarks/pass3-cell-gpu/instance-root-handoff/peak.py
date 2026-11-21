"""Peak RSS from full fresh native processes with output and digest checks."""
import argparse,json,re,subprocess
from pathlib import Path
from statistics import median
from runpy import run_path

HERE=Path(__file__).resolve().parent
study=run_path(str(HERE/"study.py"))
settings=study["settings"]
source=study["source"]


def measure(a):
    a.out.mkdir(parents=True,exist_ok=False)
    results={}
    measured=json.loads(a.timing.read_bytes())
    for case,report in measured.items():
        program,plans,req=source.common.config(a,case)
        cfg=settings(req,a)
        raw={name:[] for name in cfg}
        for lap in range(4):
            for name in list(cfg) if lap%2 else reversed(cfg):
                cmd=["/usr/bin/time","-l",a.native,program,plans]
                done=subprocess.run(cmd,input=json.dumps(dict(cfg[name],audit=False))+"\n",
                                    text=True,capture_output=True,check=True)
                v=json.loads(done.stdout)
                assert v["state_sha"]==report[name]["state_sha"] and v["runs"]==report["vanilla"]["runs"]
                assert v["root_recipe"]["allocated"]==report[name]["root_allocated"]
                assert v["multi"]["instance_claims"]==report[name]["normal_claims"]
                rss=int(re.search(r"^\s*(\d+)\s+maximum resident set size",done.stderr,re.M)[1])
                if lap:raw[name].append(rss)
        results[case]={n:dict(bytes=v,median_bytes=median(v)) for n,v in raw.items()}
        (a.out/"rss.json").write_text(json.dumps(results,indent=1)+"\n")
        print(case,results[case],flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("exp","native","timing","out"):p.add_argument(name,type=Path)
    a=p.parse_args();a.seed=1703;a.cap=8192
    a.policy=json.loads((HERE.parent/"speculative-allocation-policy/policy.json").read_bytes())
    a.fraction=json.loads((HERE.parent/"wave-demand-policy/policy.json").read_bytes())["models"]["fraction"]
    measure(a)

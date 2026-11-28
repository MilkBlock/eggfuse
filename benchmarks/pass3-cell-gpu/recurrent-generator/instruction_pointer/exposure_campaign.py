"""Resume the prespecified native evaluation queue by content-addressed evidence keys."""
import argparse
import os
from pathlib import Path
import subprocess
import time

from exposure_worlds import HELD


def models():
    starts = ["random","history","local-s71-t100000","center-s71-t100000",
              "layer03-s71-t100000","local-s113-t100000"]
    additions = [
        (group, f"{arm}-s{seed}-t{budget}")
        for group, arm, seed, budgets in (
            ("A","local",71,(250000,500000,1000000)),
            ("A","center",71,(250000,)),("A","layer03",71,(250000,)),
            ("B","local",71,(250000,)),("C","local",71,(250000,)),
            ("D","local",71,(250000,500000)),
            ("A","local",113,(250000,)),("D","local",113,(250000,)))
        for budget in budgets]
    return starts + [group+"/"+tag for group,tag in additions]


def call(script, model, cases, **kw):
    env = dict(os.environ, EXPOSURE_MODELS=model, EXPOSURE_CASES=" ".join(cases), **kw)
    subprocess.run(["sh","partner_index_reproduce.sh",script,"evaluate"],env=env,check=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--suite",choices=["development","held"],required=True)
    p.add_argument("--partial",action="store_true",help="evaluate available checkpoints and return")
    a=p.parse_args()
    out=Path(os.environ["PARTNER_INDEX_OUT"])/"continuation-exposure"
    if a.suite=="held" and not all((out/name).exists() for name in ["corpora.json","split.json"]):
        raise ValueError("freeze development data and the program/model split before any test evaluation")
    cases=("sum-divisors","fact","loopfact") if a.suite=="development" else HELD
    pending=models()
    while pending:
        ready=[name for name in pending if "/" not in name or (out/(name+".json")).exists()]
        for name in ready:
            print(a.suite,name,flush=True)
            call("exposure_eval.py",name,cases,EXPOSURE_FULL="1")
            if a.suite=="development":
                if name not in ("random","history"):
                    call("exposure_probes.py",name,cases)
                if name in ("local-s71-t100000","A/local-s71-t1000000","C/local-s71-t250000","D/local-s71-t500000"):
                    call("exposure_divergence.py",name,("sum-divisors",))
                if name in ("random","local-s71-t100000","A/local-s71-t1000000"):
                    call("exposure_eval.py",name,("sum-divisors",),EXPOSURE_UNIQUE="0",EXPOSURE_FULL="1")
            pending.remove(name)
        if a.partial:
            break
        if pending:
            time.sleep(30)


if __name__=="__main__":
    main()

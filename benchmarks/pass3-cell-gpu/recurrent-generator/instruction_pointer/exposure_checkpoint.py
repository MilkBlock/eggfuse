"""Record replayable training lineage in Git without checking in binary weights or optimizer data."""
import argparse
import json
from pathlib import Path
import subprocess
import time

from exposure_campaign import models
from exposure_train import sha


def run(out, dest, commit, once):
    expected=[name for name in models() if "/" in name]
    while expected:
        for name in expected.copy():
            p=out/(name+".json")
            if not p.exists():
                continue
            row=json.loads(p.read_text())
            info=json.loads((p.parent/(p.stem.rsplit("-t",1)[0]+"-start.json")).read_text())
            artifact=dest/(name.replace("/","-")+".json")
            if not artifact.exists():
                artifact.parent.mkdir(exist_ok=True,parents=True)
                body={k:v for k,v in row.items() if k not in ("learning_curve","calibration","gradient_tensors")}
                body.update(model=name, start=info, results_sha256=sha(p), exposed_names_sha256=sha(p.with_suffix(".seen.gz")),
                            weights_sha256=sha(p.with_suffix(".pt")))
                artifact.write_text(json.dumps(body,indent=2,sort_keys=True)+"\n")
            if commit:
                state=subprocess.check_output(["git","status","--short","--",artifact],text=True)
                if state:
                    subprocess.run(["git","add","--",artifact],check=True)
                    subprocess.run(["git","-c","core.hooksPath=/dev/null","commit","--only","-m",
                                    "data(scaling): record "+name+" training checkpoint","--",artifact],check=True)
            expected.remove(name)
        if once:
            return
        if expected:
            time.sleep(30)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("out",type=Path)
    p.add_argument("dest",type=Path)
    p.add_argument("--commit",action="store_true")
    p.add_argument("--once",action="store_true")
    a=p.parse_args()
    run(a.out,a.dest,a.commit,a.once)

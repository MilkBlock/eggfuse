"""Check independent watermarks, different RHS slots and an inactive sibling."""
import argparse
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from compare import compare

HERE = Path(__file__).resolve().parent


def check(args, tmp, across):
    tmp.mkdir()
    source = HERE/"family-watermarks.egg"
    if across:
        text=source.read_text().replace("(seq (run a) (run add2)", "(seq (run a) (run b) (run add2)")
        source=tmp/"across.egg"
        source.write_text(text)
    subprocess.run([args.compiler, "compile", "--source", source,
                    "--output", tmp/"bundle"],check=True,capture_output=True)
    program=tmp/"bundle"/"program.json"
    plans=tmp/"plans.json"
    plans.write_text("[]")
    reference=json.loads(subprocess.check_output([args.reference,program,plans],
                         input=b'{"baseline":true,"audit":true}\n'))
    for mode in ("leaf","shared","carry"):
        enabled=mode!="leaf"
        env=os.environ.copy()
        env.pop("EGGFUSE_SIGN_SAME_QUERY",None)
        env.pop("EGGFUSE_CARRY_SAME_QUERY",None)
        if mode=="carry":env["EGGFUSE_CARRY_SAME_QUERY"]="1"
        if enabled:
            env["EGGFUSE_SIGN_SAME_QUERY"]="1"
        arm=json.loads(subprocess.check_output([args.native,program,HERE/"scalar-model.json"],env=env))
        audit=compare(arm,reference)
        # Adding the early b Run gives b a first opportunity to reuse a;
        # it also aligns their later delta watermarks.
        expected = {"leaf": (0, 0), "shared": (1, 0),
                    "carry": (4, 2) if across else (2, 1)}
        observed = (arm["projected_commits"], arm["cross_run"])
        checks = ("rhs", "writes", "state_sha", "schedule", "mutation_trace")
        if (arm["failure"] or not all(audit["checks"][k] for k in checks)
                or observed != expected[mode]
                or arm["family_fanout"].get("2", 0) != arm["projected_commits"]):
            raise ValueError((across, mode, observed, expected[mode], audit["checks"]))
    print("Run-boundary fixture passed", "across" if across else "same Run")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ("compiler","native","reference"):
        p.add_argument(arg,type=Path)
    with TemporaryDirectory() as tmp:
        args=p.parse_args()
        check(args,Path(tmp)/"same",False)
        check(args,Path(tmp)/"across",True)

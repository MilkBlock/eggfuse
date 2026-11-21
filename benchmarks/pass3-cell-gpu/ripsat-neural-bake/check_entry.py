"""Exercise normal Bake publication/reload and fail-closed cache handling on real artifacts."""
import argparse
import hashlib
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
entry=HERE.parent/"explicit-parent-cell-composition/bake.py"
loader=run_path(str(entry))["ripsat"]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def run(a):
    a.out.mkdir(parents=True,exist_ok=False)
    targets=a.exp/"compact-holdouts-20261121-v1"
    donors={c:targets/(c+"-1703")/"program.json" for c in ("dot-product","jacobi-1d")}
    target=targets/"sum-bits-1703/program.json"
    other=a.exp/"extra-pass3-transfer-v1/3mm-1703/program.json"
    library=a.out/"library.json"
    cmd=[sys.executable,str(entry),"ripsat","--evidence",str(HERE.parent/"ripsat-donor-evidence/evidence.json")]
    for c,p in donors.items():cmd+=["--donor",f"{c}={p}"]
    cmd+=["--target",str(target),"--out",str(library)]
    subprocess.run(cmd,check=True)
    verified=loader["load_checked"](library,target)
    assert verified["strict_named"]["library"]
    stable=sha(library)
    def fail_cli(args,message):
        proc=subprocess.run(args,capture_output=True,text=True)
        assert proc.returncode and message in proc.stderr,(proc.returncode,proc.stderr)
        assert sha(library)==stable
    fail_cli([*cmd,"--donor",f"dot-product={donors['dot-product']}"],"duplicate donor")
    fail_cli([*cmd,"--out",str(target)],"overwrite an input")
    def fail_load(file,target,error):
        try:
            loader["load_checked"](file,target)
        except ValueError as exc:
            assert error in str(exc),(error,str(exc))
        else:
            raise AssertionError(error)
    fail_load(library,other,"different target")
    # A syntactically connected second edge cannot be inserted by editing the cache.
    tamper=json.loads(library.read_bytes())
    tamper["strict_named"]["depth"]=2
    tamper["strict_named"]["library"].append([[143,1,55],[55,1,143]])
    false_lib=a.out/"extended.json"
    false_lib.write_text(json.dumps(tamper))
    fail_load(false_lib,target,"disagrees")
    receipt=dict(target_sha=sha(target),evidence_sha=verified["evidence_sha256"],
                 trust_sha=verified["trust_index_sha256"],strict_named=verified["strict_named"],
                 negative=["duplicate donor","output aliases target","foreign target","cache adds unproved second edge"])
    (a.out/"entry-checks.json").write_text(json.dumps(receipt,indent=1)+"\n")
    print("Revalidated cached proof; rejected all four invalid entrypoint calls.")

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("exp",type=Path);p.add_argument("out",type=Path)
    run(p.parse_args())

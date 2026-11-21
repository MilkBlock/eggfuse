"""Smoke-test the normal CLI, cached authorization, and capability refusal on real sum-bits."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent

def cli(args, expected=None):
    result = subprocess.run([sys.executable, *map(str, args)], text=True, capture_output=True)
    if expected is None:
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
    elif result.returncode == 0 or expected not in result.stderr:
        raise AssertionError((result.returncode, result.stderr, expected))
    return result

def run(a):
    a.out.mkdir(parents=True, exist_ok=False)
    inputs = a.exp / "compact-holdouts-20261121-v1"
    target = inputs / "sum-bits-1703/program.json"
    cache = a.out / "cached.json"
    build = [HERE / "bake.py", "ripsat", "--evidence", BENCH / "ripsat-donor-evidence/evidence.json",
             "--target", target]
    for donor in ("dot-product", "jacobi-1d"):
        build.extend(["--donor", f"{donor}={inputs / (donor+'-1703') / 'program.json'}"])
    cli([*build, "--out", cache, "--set-publication"])
    artifact = json.loads(cache.read_bytes())
    checked = json.loads((BENCH / "ripsat-publication-chain/sum-bits.json").read_bytes())
    assert artifact["set_publication_authorization"] == checked
    def study(binary, library, name, flag=True):
        cmd = [BENCH / "filtered-explicit-parent/study.py", a.exp, binary,
               BENCH / "filtered-explicit-parent/library.json", a.out / name,
               "--cases", "sum-bits", "--ripsat-library", library, "--repeats", "1"]
        return cmd + (["--set-publication"] if flag else [])
    cli(study(a.native, cache, "positive"))
    rows = json.loads((a.out/"positive/results.json").read_bytes())["sum-bits"]["arms"]
    before, after = rows["ripsat"], rows["ripsat_set"]
    c = after["stats"]["set_publication"]
    assert c["published"] > 0 and c["confirmed"] == before["packets"]-after["packets"] > 0
    assert c["confirmed"] == after["by_depth"][1][2] and before["state_sha"] == after["state_sha"]
    cli(study(a.old_native, cache, "old"), "--set-publication requires the ripsat-set-receipt native runtime")
    tampered=json.loads(cache.read_bytes())
    tampered["set_publication_authorization"]["strict_named"]["set_publication"]["path"][1][1]=0
    stale=dict(artifact,target_sha256="0"*64)
    for name,obj,message in (("tampered",tampered,"disagrees with its checked build evidence"),
                             ("stale",stale,"different target")):
        path=a.out/(name+".json");path.write_text(json.dumps(obj))
        cli(study(a.native,path,name),message)
    plain=a.out/"plain.json";cli([*build,"--out",plain])
    assert "set_publication_authorization" not in json.loads(plain.read_bytes())
    cli(study(a.native,plain,"no-grant"),"cache has no Set publication authorization")
    cli(study(a.old_native,cache,"default",False))
    ordinary=json.loads((a.out/"default/results.json").read_bytes())["sum-bits"]["arms"]
    assert "ripsat_set" not in ordinary and ordinary["ripsat"]["state_sha"]==before["state_sha"]
    print(f"sum-bits {c['published']} fresh Set publications, {c['confirmed']} terminal commits, "
          f"{before['packets']} -> {after['packets']} packets; old-native, stale, tampered and missing-grant refusals passed")
if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ("exp","native","old_native","out"):
        parser.add_argument(arg,type=Path)
    run(parser.parse_args())

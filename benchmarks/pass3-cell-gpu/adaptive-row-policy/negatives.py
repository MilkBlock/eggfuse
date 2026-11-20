"""Exercise compact row pages against corrupted envelopes at full source execution."""

import argparse
import json
import subprocess
from pathlib import Path

from runner import materialize, read, rpc


def run(a):
    a.out.mkdir(parents=True, exist_ok=False)
    results = {}
    for case in ("sum-bits", "dot-product"):
        image, plans, original, req = materialize(a.exp, a.out, case, 1703, "certified")
        with subprocess.Popen(
            [a.binary, image, plans],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as proc:
            pair = {}
            for fmt in ("full", "shared_wire", "resident", "checked_slots"):
                for mode in (
                    "use",
                    "wrong-port",
                    "wrong-template",
                    "shadow",
                    "withhold",
                ):
                    root = a.out / f"{case}-{fmt}-{mode}.json"
                    root.write_text(
                        json.dumps(
                            {"control": mode, "forbid_fallback": False, "encoding": fmt}
                        )
                    )
                    v = rpc(
                        proc,
                        dict(
                            req,
                            root_config=str(root),
                            rows={
                                "action": 4,
                                "max_rows": 1,
                                "workers": 1,
                                "batch": True,
                            },
                            audit=True,
                        ),
                    )
                    assert "source_error" not in v
                    src = read(original / "rhs.json")
                    assert src == v["rhs"]
                    assert (
                        read(original / "resumes.json") == v["resumes"]
                        and read(original / "writes.json") == v["writes"]
                    )
                    r = v["root_recipe"]
                    old = pair.get("full/use")
                    if old:
                        assert old["proposal_hash"] == r["raw_hash"]
                    if mode != "use":
                        assert r["allocated"] == 0 and r["applied"] == 0
                    pair[fmt + "/" + mode] = {
                        "allocated": r["allocated"],
                        "applied": r["applied"],
                        "sealed": r["sealed"],
                        "rejected": r["rejected"],
                        "proposal_hash": r["raw_hash"],
                        "wire": r["wire_bytes"],
                        "state": v["state_sha"],
                    }
            results[case] = pair
            (a.out / "results.json").write_text(json.dumps(results, indent=1) + "\n")
            proc.stdin.close()
            proc.wait()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("binary", "exp", "out"):
        p.add_argument(k, type=Path)
    run(p.parse_args())

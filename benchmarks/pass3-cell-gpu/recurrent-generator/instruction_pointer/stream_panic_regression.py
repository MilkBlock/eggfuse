"""Reproduce the source assertion using the original native receiver, offline."""

import json
import subprocess
import tempfile
from pathlib import Path

import torch

from recursive_rollout import online
from recursive_train import binary, folder, read


def regression(root):
    work = root / "cell-stream" / "panic"
    result = online(root, "sum-divisors", "pending", work)
    assert result["failed_run"] == 177 and result["termination"] == "execution_failure"
    source = folder(root, "sum-divisors")
    failed = read(work / "failed-issued.json")
    prefix = read(work / "issued.json")
    assert failed["requests"][: len(prefix["requests"])] == prefix["requests"]
    batch = failed["requests"][len(prefix["requests"]) :]
    rows = read(work / "state.json")["rows"]
    # Independent check of the actual source assertion on the exported snapshot.
    expect = [
        r["values"] for r in rows if r["table"] == "ExpectType" and not r["subsumed"]
    ]
    actual = [
        r["values"] for r in rows if r["table"] == "HasType" and not r["subsumed"]
    ]
    mismatches = [
        (a, b) for a in expect for b in actual if a[0] == b[0] and a[1] != b[1]
    ]
    assert len(mismatches) == 1
    with tempfile.TemporaryDirectory() as tmp:
        verdicts = []
        for q in batch:
            tape = Path(tmp) / "probe.json"
            tape.write_text(
                json.dumps({**prefix, "requests": prefix["requests"] + [q]})
            )
            run = subprocess.run(
                [binary(root), "replay", source / "program.json", tape, "audit", "177"],
                capture_output=True,
                text=True,
            )
            if run.returncode:
                assert "source panic (Run 177, rule 351, op 0," in run.stderr
            verdicts.append(
                {
                    "token": q["token"],
                    "parents": q["parents"],
                    "source_asserted": bool(run.returncode),
                }
            )
    assert any(v["source_asserted"] for v in verdicts) and result["failed_paid"] == len(
        failed["requests"]
    )
    exact = json.loads(
        subprocess.check_output(
            [
                binary(root),
                "replay",
                source / "program.json",
                work / "issued.json",
                "time",
                "176",
                "--audit-exact-next",
            ]
        )
    )
    assert exact["prefix_sha"] == result["state_sha"]
    assert "source panic (Run 177, rule 351, op 0," in exact["result"]["source_error"]
    return dict(
        mismatch=mismatches,
        exact_continuation=exact,
        isolated=verdicts,
        error=result["failure"],
        completed_runs=result["runs"],
    )


if __name__ == "__main__":
    import sys

    torch.set_num_threads(1)
    print(json.dumps(regression(Path(sys.argv[1]).resolve()), indent=2))

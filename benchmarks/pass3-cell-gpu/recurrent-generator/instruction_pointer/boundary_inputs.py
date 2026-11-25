"""Offline native audit of a frozen network tape and its actual per-Run opportunity sets."""

import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from recursive_train import binary, folder, read
from scaling_bake import save

BASE = Path("run-recall/region-ownership")
CASE = "sum-divisors"


def frozen_tape():
    with (BASE / "neural-prefixes.jsonl").open() as f:
        return next(row for row in map(json.loads, f) if row["series"].startswith(CASE + "-"))


def native(exe, *args):
    return json.loads(subprocess.check_output([exe, *args]))


def collect(root, out):
    d = folder(root, CASE)
    saved = frozen_tape()
    exe = binary(root)
    with TemporaryDirectory(dir=out) as tmp:
        path = Path(tmp) / "tape.json"
        save(path, saved["tape"])
        for label, ledger in [("model", path), ("teacher", d / "tape.json")]:
            flags = ["--memory", out / "model-memory.jsonl"] if label == "model" else []
            report = native(exe, "replay", d / "program.json", ledger, "audit", *flags, "--ept-origins")
            if label == "model":
                with (BASE / "runs.jsonl").open() as f:
                    gold = next(
                        q
                        for q in map(json.loads, f)
                        if (q["case"], q["label"], q["mode"]) == (CASE, "routes32", "E")
                    )
                if report["state_sha"] != gold["state_sha"]:
                    raise ValueError("frozen rollout replay changed graph")
            elif report["state_sha"] != read(d / "capture.json")["state_sha"]:
                raise ValueError("teacher replay changed graph")
            save(out / (label + "-credit.json"), report["ept"])
        exact = {}
        tape = saved["tape"]
        for run, rules in saved["schedule"]:
            if not rules:
                continue
            save(
                path,
                dict(
                    tape,
                    requests=[q for q in tape["requests"] if q["run"] < run],
                    repair_events=[e for e in tape["repair_events"] if e["visible_from_run"] <= run],
                ),
            )
            proofs = native(
                exe, "replay", d / "program.json", path, "time", str(run - 1), "--audit-next-proofs"
            )
            if any(q["run"] != run or q["rule"] not in rules for q in proofs):
                raise ValueError("unexpected next-proof schedule")
            exact[run] = proofs
        save(out / "exact.json", exact)
    return saved

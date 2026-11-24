"""Time a full native reference and a validated, search-free offline teacher tape."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from statistics import median
from time import perf_counter


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def survey(binary, program, scratch):
    tape = scratch / "tape.json"
    limit = []
    scope = "full schedule"

    def run(role, mode):
        start = perf_counter()
        p = subprocess.run(
            [binary, role, program, "-" if role == "reference" else tape, mode, *limit],
            capture_output=True,
            timeout=120,
        )
        elapsed = perf_counter() - start
        if p.returncode:
            raise ValueError(f"{role} {mode}: {p.stderr.decode()[-400:]}")
        result = json.loads(p.stdout)
        result["wall"] = elapsed
        return result

    reference = run("reference", "audit")

    def validate(d, audited):
        keys = ["schedule", "matches", "runs", "state_sha"]
        if audited:
            keys.extend(["rhs", "writes", "events", "resumes"])
        for k in keys:
            if d[k] != reference[k]:
                raise ValueError(f"{d['role']} diverged in {k}")
        if d["role"] == "replay" and (
            d["unused"]
            or d["counts"]["accepted"] != d["matches"]
            or d["counts"]["duplicates"]
            or any(d["counts"]["rejected"].values())
        ):
            raise ValueError("teacher payment failed")

    validate(run("capture", "audit"), True)
    try:
        validate(run("replay", "audit"), True)
    except ValueError as exc:
        if "schedule probe requires its own named proof" not in str(exc):
            raise
        # Require the full exact postcondition run to agree on *all* inference
        # steps and the final graph with both endpoints of the timed prefix.
        scope = "all inference Runs; trailing check executed only by full reference"
        limit = [str(reference["runs"])]
        validate(run("reference", "audit"), True)
        validate(run("replay", "audit"), True)
    rounds = []
    for order in [("reference", "replay"), ("replay", "reference")] * 2:
        row = {}
        for role in order:
            d = run(role, "time")
            validate(d, False)
            row[role] = {
                k: d[k]
                for k in (
                    "seconds",
                    "wall",
                    "source_search_phase_seconds",
                    "rhs_phase_seconds",
                    "repair_phase_seconds",
                    "verify_seconds",
                )
                if k in d
            }
        rounds.append(row)
    ratio = lambda key: [r["reference"][key] / r["replay"][key] for r in rounds]
    return dict(
        scope=scope,
        program=digest(program),
        receiver=digest(binary),
        tape=digest(tape),
        runs=reference["runs"],
        commits=reference["matches"],
        state_sha=reference["state_sha"],
        rounds=rounds,
        engine_ratio=median(ratio("seconds")),
        wall_ratio=median(ratio("wall")),
        oracle_wall_wins=sum(x > 1 for x in ratio("wall")),
        oracle_engine_wins=sum(x > 1 for x in ratio("seconds")),
        zero_search_bound=median(
            r["reference"]["seconds"]
            / (
                r["reference"]["seconds"]
                - r["reference"]["source_search_phase_seconds"]
            )
            for r in rounds
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("receiver", type=Path)
    p.add_argument("program", type=Path)
    p.add_argument("out", type=Path)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    answer = survey(a.receiver.resolve(), a.program.resolve(), a.out)
    (a.out / "survey.json").write_text(json.dumps(answer, indent=2) + "\n")

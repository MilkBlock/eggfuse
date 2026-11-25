"""Audit duplicate insertion against all subsequent native publications and the actual terminal graph."""

import argparse
import json
import subprocess
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from latent_cell_flow import TEST, TRAIN, VALID
from recursive_train import binary, folder, read


def file_hash(p):
    h = sha256()
    with p.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def audit(root, forks, rollout, out):
    all_results = {}
    for name in (*TRAIN, VALID, *TEST):
        d = folder(root, name.removesuffix("-roll"))
        tape = read(rollout / "sum-issued.json" if name == "sum-roll" else d / "tape.json")
        chosen = {
            r["a"]["token"]: r for r in map(json.loads, (forks / (name + ".jsonl")).read_text().splitlines())
        }
        requests = tape["requests"]
        uid = max(q["token"] for q in requests) + 1
        plus = []
        for q in requests:
            plus.append(q)
            if q["token"] in chosen:
                plus.append({**q, "token": uid})
                uid += 1
        with TemporaryDirectory(dir=out) as tmp:
            w = Path(tmp)
            reports = []
            hashes = []
            for qs in (requests, plus):
                t = w / "tape"
                t.write_text(json.dumps({**tape, "requests": qs}))
                m = w / "memory"
                reports.append(
                    json.loads(
                        subprocess.check_output(
                            [binary(root), "replay", d / "program.json", t, "audit", "--memory", m, "--ept"]
                        )
                    )
                )
                hashes.append(file_hash(m))
        a, b = reports
        same = {
            k: a[k] == b[k] for k in ("schedule", "state_sha", "rhs", "writes", "resumes", "events", "ept")
        }
        if (
            not all(same.values())
            or hashes[0] != hashes[1]
            or b["counts"]["duplicates"] - a["counts"]["duplicates"] != len(chosen)
        ):
            raise ValueError((name, same, hashes, a["counts"], b["counts"]))
        all_results[name] = dict(
            runs=a["runs"],
            verified_repeats=len(chosen),
            publication_sha=hashes[0],
            terminal=a["state_sha"],
            checks=same,
        )
        (out / "suffix-audit.json").write_text(json.dumps(all_results, indent=2))
        print(name, len(chosen), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for name in ("root", "forks", "rollout", "out"):
        p.add_argument(name, type=Path)
    a = p.parse_args()
    audit(a.root, a.forks, a.rollout, a.out)

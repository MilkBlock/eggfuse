"""Offline native forks. No expert search or replay data is used by a live generator."""

import argparse
import json
import random
import subprocess
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory

from recursive_train import read


def by_run(requests):
    groups = defaultdict(list)
    for req in requests:
        groups[req["run"]].append(req)
    return groups


def snapshot(exe, program, tape, path, requests, run):
    trial = path / "trial.json"
    trial.write_text(json.dumps({**tape, "requests": requests}, separators=(",", ":")))
    memory = path / "memory.jsonl"
    raw = subprocess.check_output([exe, "replay", program, trial, "audit", str(run + 1), "--memory", memory])
    outcome = json.loads(raw)
    with memory.open() as src:
        frames = [json.loads(line) for line in src]
    if len(frames) < 2 or frames[-1]["run"] != run + 1:
        return None
    return frames[-2], frames[-1], outcome["counts"]


def collect(exe, directory, tape_path, memory_path, dest, limit, seed):
    rng = random.Random(seed)
    tape = read(tape_path)
    groups = by_run(tape["requests"])
    candidates = []
    frames = {}
    with memory_path.open() as src:
        for line in src:
            f = json.loads(line)
            frames[f["run"]] = f
    for run, requests in groups.items():
        if run + 1 not in frames:
            continue
        pool = [q for q in requests if q["parents"]]
        if len(pool) >= 2:
            candidates.append((run, pool))
    rng.shuffle(candidates)
    with TemporaryDirectory(dir=dest.parent) as tmp, dest.open("w") as output:
        for run, pool in sorted(candidates[:limit]):
            a = rng.choice(pool)
            other = [q for q in pool if q["token"] != a["token"]]
            peers = [q for q in other if q["rule"] == a["rule"] and q["parents"] != a["parents"]]
            b = rng.choice(peers or other)
            dup = {**a, "token": max(q["token"] for q in tape["requests"]) + 1}
            # Deliberately stale/missing version; the native verifier supplies its label.
            bad = {
                **dup,
                "parents": [
                    {**a["parents"][0], "version": a["parents"][0]["version"] + 1},
                    *a["parents"][1:],
                ],
            }
            prior = [q for q in tape["requests"] if q["run"] < run]
            background = (
                [q for q in pool if q not in (a, b)][:1] if directory.name.startswith("grammar") else []
            )
            cases = {}
            for key, tail in (
                ("empty", []),
                ("a", [a]),
                ("aa", [a, dup]),
                ("b", [b]),
                ("ab", [a, b]),
                ("ba", [b, a]),
                ("bad", [bad]),
            ):
                result = snapshot(
                    exe, directory / "program.json", tape, Path(tmp), prior + background + tail, run
                )
                if result is None:
                    break
                before, after, counts = result
                for name in ("updates", "retired", "epoch", "rules"):
                    if before[name] != frames[run][name]:
                        raise ValueError((run, name, "fork differs from recorded state"))
                cases[key] = {"frame": after, "counts": counts}
            if len(cases) != 7:
                print(f"Run {run}: unknown; fork lacks common publication")
                continue
            output.write(
                json.dumps(
                    dict(background=background, run=run, a=a, b=b, bad=bad, cases=cases),
                    separators=(",", ":"),
                )
                + "\n"
            )
            output.flush()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for name in ("exe", "directory", "tape", "memory", "dest"):
        p.add_argument(name, type=Path)
    p.add_argument("--contexts", type=int, default=16)
    p.add_argument("--seed", type=int, default=4621)
    a = p.parse_args()
    collect(a.exe, a.directory, a.tape, a.memory, a.dest, a.contexts, a.seed)

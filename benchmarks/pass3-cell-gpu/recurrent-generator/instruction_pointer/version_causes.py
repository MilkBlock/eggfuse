"""Matched native interventions on the seal that published each requested revision.
All arms share a complete original prefix. Matching compares the whole named observation.
"""

import argparse
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from boundary_inputs import CASE, binary, folder, read
from scaling_bake import save

PRIOR = Path("run-recall/startup-boundaries")


class Interventions:
    def __init__(self, root, tmp):
        self.exe = binary(root)
        self.d = folder(root, CASE)
        self.tape = read(self.d / "tape.json")
        self.by = defaultdict(list)
        for q in self.tape["requests"]:
            self.by[q["run"]].append(q)
        self.cached = {}
        self.tmp = tmp

    def observation(self, run, keep):
        key = run, tuple(sorted(keep))
        if key not in self.cached:
            tape = [
                q
                for q in self.tape["requests"]
                if q["run"] < run or (q["run"] == run and q["token"] in keep)
            ]
            file = self.tmp / "trial.json"
            mem = self.tmp / "memory.jsonl"
            save(file, dict(self.tape, requests=tape, repair_events=[]))
            cmd = [
                self.exe,
                "replay",
                self.d / "program.json",
                file,
                "time",
                str(run + 1),
                "--memory",
                mem,
            ]
            report = json.loads(subprocess.check_output(cmd))
            if report["counts"]["accepted"] != len(tape):
                raise RuntimeError(("counterfactual prefix rejected", key))
            current = {}
            found = False
            with mem.open() as stream:
                for f in map(json.loads, stream):
                    for a in f["retired"]:
                        current.pop((a["token"], a["op"]), None)
                    current.update(
                        {(a["token"], a["op"]): row for a, row in f["updates"]}
                    )
                    if f["run"] == run + 1:
                        found = True
                        break
            if not found:
                raise RuntimeError(("missing observation at publication", key))
            self.cached[key] = current
        return self.cached[key]


def classify(inside, outside, empty):
    if empty:
        return "no_request_needed_on_this_seal"
    if inside and outside:
        return "both_sufficient_alternatives"
    if inside:
        return "inside_sufficient"
    if outside:
        return "outside_sufficient"
    return "mixed_required"


def audit(root, out):
    cases = read(PRIOR / "versions.json")
    sets = {
        r["root"]: set(r["region"]["tokens"])
        for r in read(PRIOR / "boundaries.json")
        if r["label"] == "both_ancestries"
    }
    started = perf_counter()
    results = []
    with TemporaryDirectory() as d:
        probes = Interventions(root, Path(d))
        for r in cases:
            # Multiple slots may read the very same publication.
            targets = defaultdict(list)
            for e in r["timelines"]:
                first_run = next(n for n, v in e["timeline"] if v == e["requested"])
                targets[first_run - 1, e["src"], e["op"], e["requested"]].append(
                    [e["consumer"], e["slot"]]
                )
            for (run, src, pc, version), uses in targets.items():
                addr = src, pc
                full = {q["token"] for q in probes.by[run]}
                inside = full & sets[r["root"]]
                gold = probes.observation(run, full)[addr]
                if gold["version"] != version:
                    raise ValueError("wrong native control version")

                def test(subset):
                    return probes.observation(run, subset).get(addr) == gold

                flags = [test(s) for s in (inside, full - inside, set())]
                single = [t for t in sorted(full) if test({t})] if not flags[2] else []
                results.append(
                    dict(
                        root=r["root"],
                        address=[src, pc],
                        version=version,
                        seal=run,
                        consumers=uses,
                        inside=sorted(inside),
                        outside=sorted(full - inside),
                        matches=flags,
                        kind=classify(*flags),
                        sufficient_single_requests=single,
                        observation=gold,
                    )
                )
            print(r["root"], len(probes.cached), flush=True)
        save(
            out / "causes.json",
            dict(
                executions=len(probes.cached),
                wall=perf_counter() - started,
                rows=results,
                counts=Counter(row["kind"] for row in results),
            ),
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    args = p.parse_args()
    audit(args.root, args.out)

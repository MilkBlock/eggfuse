"""Read-only alignment of visible final rows by finite named constructor witnesses."""

import argparse
import json
import subprocess
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory

from recursive_train import binary, folder, read


def atom(v):
    return (
        (v["sort"], json.dumps(v.get("value"), sort_keys=True))
        if "eq" not in v
        else (v["sort"], v["eq"])
    )


class Target:
    def __init__(self, program, reference):
        self.constructors = {
            t["name"] for t in program["recipe"]["tables"] if t["kind"] == "constructor"
        }
        self.gold = [
            (
                r["table"],
                tuple(atom(v) for v in r["values"]),
                tuple("eq" in v for v in r["values"]),
            )
            for r in reference["rows"]
            if not r["subsumed"]
        ]
        self.paths = []
        # Choose one reference ground term per class, increasing by term height.
        known = set()
        while True:
            step = {}
            for table, vs, eq in self.gold:
                if table not in self.constructors or not eq[-1] or vs[-1] in known:
                    continue
                if all(not flag or v in known for v, flag in zip(vs[:-1], eq[:-1])):
                    step.setdefault(vs[-1], (table, vs[:-1], eq[:-1]))
            if not step:
                break
            self.paths.append(step)
            known.update(step)

    def match(self, state):
        idx = {}
        visible = set()
        for row in state["rows"]:
            if row["subsumed"]:
                continue
            table = row["table"]
            values = tuple(atom(x) for x in row["values"])
            visible.add((table, values))
            if table in self.constructors:
                idx[table, values[:-1]] = values[-1]
        mapped = {}
        for step in self.paths:
            for target, (table, args, eq) in step.items():
                key = tuple(mapped.get(v) if e else v for v, e in zip(args, eq))
                if (table, key) in idx:
                    mapped[target] = idx[table, key]
        reverse = defaultdict(set)
        for source, dest in mapped.items():
            reverse[dest].add(source)
        # A new live merge can coalesce two distinct reference classes. Avoid
        # giving both of those classes full semantic credit for a single live row.
        good = {k: v for k, v in mapped.items() if len(reverse[v]) == 1}
        return {
            i
            for i, (table, vs, eq) in enumerate(self.gold)
            if (table, tuple(good.get(v) if flag else v for v, flag in zip(vs, eq)))
            in visible
        }


def snapshot(root, d, mode, tape, stop, output, *, ept=False):
    cmd = [binary(root), mode, d / "program.json", tape, "time"]
    if stop is not None:
        cmd.append(str(stop))
    cmd.extend(["--export", output])
    if ept:
        cmd.append("--ept")
    report = json.loads(subprocess.check_output(cmd))
    return read(output), report


def coverage(root, case, arms):
    d = folder(root, case)
    out = root / "recursive-agent"
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "state.json"
        ref, report = snapshot(root, d, "reference", "-", None, path)
        goal = Target(read(d / "program.json"), ref)
        den = len(goal.gold)
        self_hits = len(goal.match(ref))
        initial, _ = snapshot(root, d, "reference", "-", 0, path)
        seed = goal.match(initial)
        results = {}
        sched = report["schedule"]

        def coord(s):
            return (s[0], tuple(s[1]), tuple(s[2]))

        coordinates = {coord(s): j + 1 for j, s in enumerate(sched)}
        assert len(coordinates) == len(sched)

        def history(mode, tape, stop, expected, dest):
            cmd = [binary(root), mode, d / "program.json", tape, "time"]
            if stop is not None:
                cmd.append(str(stop))
            res = json.loads(subprocess.check_output(cmd + ["--row-history", dest]))
            assert res["state_sha"] == expected
            return res["schedule"]

        def observed(dest):
            rows = {}
            covered = set()
            with dest.open() as stream:
                for f in map(json.loads, stream):
                    if f["added"] or f["removed"] or f["run"] == 0:
                        for r in f["removed"]:
                            del rows[r]
                        for r in f["added"]:
                            rows[r] = json.loads(r)
                        covered = goal.match({"rows": rows.values()})
                    yield f["run"], covered

        gold_file = Path(tmp) / "gold.jsonl"
        history("reference", "-", None, report["state_sha"], gold_file)
        cache = dict(observed(gold_file))
        for arm in arms:
            work = out / (case + "-" + arm)
            m = read(work / "metrics.json")
            final = goal.match(read(work / "state.json"))
            trace = m["trace"]
            n = len(trace)
            log = Path(tmp) / "online.jsonl"
            sched_live = history("replay", work / "issued.json", n, m["state_sha"], log)
            totals = []
            missing = set()
            recovered = set()
            for k, have in observed(log):
                if not k:
                    continue
                due = coordinates.get(coord(sched_live[k - 1]))
                recovered |= missing & have
                if due is not None:
                    missing |= (cache[due] - have) - seed
                t = trace[k][6] if k < n else m["wall"]
                totals.append(
                    dict(
                        run=k,
                        elapsed=t,
                        covered=len(have),
                        derived=len(have - seed),
                        due_run=due,
                        overdue=len(missing),
                        recovered=len(recovered),
                    )
                )
            assert totals[-1]["covered"] == len(final)
            results[arm] = dict(
                all=[len(final), den],
                derived=[len(final - seed), den - len(seed)],
                reference_groundable=self_hits,
                seed=len(seed),
                first_missed=len(missing),
                later_recovered=len(recovered),
                curve=totals,
            )
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("cases", nargs="+")
    p.add_argument("--arms", nargs="+", default=["two", "free", "pending", "legacy"])
    a = p.parse_args()
    root = a.root.resolve()
    for c in a.cases:
        v = coverage(root, c, a.arms)
        (root / "recursive-agent" / (c + "-coverage.json")).write_text(
            json.dumps(v, indent=2)
        )

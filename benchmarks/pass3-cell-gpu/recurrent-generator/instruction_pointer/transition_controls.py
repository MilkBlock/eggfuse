"""Paired native forks isolating pre-existing outputs from immutable input references."""

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

from ccp_v01 import Client, read_repairs
from cell_transaction import STATUS, memory_frame
from credit_scale_buffer import submit
from discrete_cells import from_q

SOURCE = """
(relation Seed (i64))
(relation L (i64))
(relation R (i64))
(ruleset fillL) (ruleset fillR) (ruleset clear) (ruleset emit) (ruleset wake)
(rule ((Seed x)) ((L x)) :ruleset fillL)
(rule ((Seed x)) ((R x)) :ruleset fillR)
(rule ((Seed x)) ((delete (L x)) (delete (R x))) :ruleset clear)
(rule ((Seed x)) ((L x) (R x)) :ruleset emit)
(rule ((Seed x)) ((Seed (+ x 1))) :ruleset wake)
(Seed 7)
(run-schedule (run fillL) (run fillR) (run clear) (run emit) (run emit) (run wake) (run emit))
"""


def trial(a, ir, branch):
    digest = hashlib.sha256(ir.read_bytes()).hexdigest()
    folder = ir.parent
    tape = folder / f"{branch}.json"

    def replay(client, run, *opts):
        tape.write_text(
            json.dumps(
                {
                    "schema": "cell-token-replay/v2",
                    "program_sha256": digest,
                    "repair_events": [],
                    "requests": list(client.offline_tape(run)),
                }
            )
        )
        return json.loads(
            subprocess.check_output(
                [a.runtime, "replay", ir, tape, "audit", str(run), *opts]
            )
        )

    observer = folder / f"{branch}-generation.jsonl"
    admission = folder / f"{branch}-issue.csv"
    env = dict(
        os.environ,
        EGGFUSE_QUERY_OBSERVER=str(observer),
        EGGFUSE_ADMISSION_OBSERVER=str(admission),
    )
    with subprocess.Popen(
        [a.runtime, "online-ccp-v0.1", ir, "-", "audit", "--ept"],
        stdin=-1,
        stdout=-1,
        env=env,
    ) as proc:
        client = Client(proc, 16, digest)
        receipts = []
        target = None
        try:
            while line := proc.stdout.readline():
                f = json.loads(line)
                if "role" in f:
                    break
                memory_frame(proc.stdout, f)
                desc, _ = read_repairs(proc.stdout, f)
                if len(desc):
                    raise ValueError("unexpected repair in immutable-key control")
                if f.get("final_publication"):
                    continue
                r = client.run = f["run"]
                client.epoch = f["epoch"]
                qs = replay(client, r - 1, "--audit-next-proofs")
                cells = [from_q(q) for q in qs]
                if (
                    r in (1, 2, 3)
                    and r
                    not in {
                        "empty": (),
                        "left": (1,),
                        "full": (1, 2),
                        "cleared": (1, 2, 3),
                        "delay": (),
                    }[branch]
                ):
                    cells = []
                if r == 4:
                    (target,) = cells
                    if branch == "delay":
                        cells = []
                if r == 5:
                    cells = [target]
                if r == 7:
                    cells = [target, *[c for c in cells if c != target]]
                rows = submit(client, cells, 16)
                client.seal()
                rep = replay(client, r, "--ept-origins")
                credit = dict(rep["ept"]["origins"])
                for c, (owner, status, *_) in zip(cells, rows, strict=True):
                    receipts.append(
                        {
                            "run": r,
                            "request": owner,
                            "rule": c.rule,
                            "refs": c.refs,
                            "status": STATUS[status],
                            "gain": credit.get(owner, 0),
                            "state": rep["state_sha"],
                        }
                    )
            assert rep["state_sha"] == f["state_sha"]
            return receipts
        finally:
            proc.stdin.close()
            client.close()
            if proc.poll() is None and "role" not in f:
                proc.kill()


def main(a):
    d = a.out / "controls"
    d.mkdir(exist_ok=True)
    path = d / "probe.egg"
    path.write_text(SOURCE)
    ir = d / "compiled/program.json"
    if not ir.exists():
        subprocess.run(
            [a.compiler, "compile", "--source", path, "--output", ir.parent],
            check=True,
            stdout=subprocess.DEVNULL,
        )
    results = {b: trial(a, ir, b) for b in ("empty", "left", "full", "cleared")}
    choices = {b: next(v for v in rows if v["run"] == 4) for b, rows in results.items()}
    assert len({(x["rule"], x["refs"]) for x in choices.values()}) == 1
    assert [v["gain"] for v in choices.values()] == [2, 1, 0, 2]
    for rows in results.values():
        assert [v["status"] for v in rows if v["run"] == 5] == ["untriggered_rule"]
        assert [v["status"] for v in rows if v["run"] == 7] == ["watermark", "accepted"]
    delayed = trial(a, ir, "delay")
    issued = next(v for v in delayed if v["run"] == 5)
    windows = [
        json.loads(line)
        for line in (ir.parent / "delay-generation.jsonl").read_text().splitlines()
    ]
    dirty = next(
        d
        for r, _, _, end, rs in windows
        if r == 4 and not end
        for rid, wm, d in rs
        if rid == issued["rule"]
    )
    observer = [
        list(map(int, line.split(",")))
        for line in (ir.parent / "delay-issue.csv").read_text().splitlines()
    ]
    run, _uid, _rid, epoch, check, issue_dirty = next(
        v for v in observer if v[1] == issued["request"]
    )
    assert (
        dirty
        and run == 5
        and check
        and not issue_dirty
        and issued["status"] == "untriggered_rule"
    )
    results["delayed_draft"] = {
        "generated_run": 4,
        "generate_dirty": dirty,
        "issue_dirty": bool(issue_dirty),
        "issue_epoch": epoch,
        "issued": issued,
    }
    (a.out / "native-controls.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for k in ("out", "runtime", "compiler"):
        p.add_argument("--" + k, type=Path, required=True)
    main(p.parse_args())

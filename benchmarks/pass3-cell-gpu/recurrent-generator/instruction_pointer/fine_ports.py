"""Offline native controls for stale named reads and unpublished in-batch dependencies."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from ccp_v01 import Client, read_repairs
from cell_transaction import STATUS, memory_frame
from credit_scale_buffer import submit
from discrete_cells import from_q
from discrete_draft import Cell
from fine_credit import labels

SOURCE = """
(relation Seed (i64)) (relation L (i64)) (relation R (i64)) (relation Seen (i64))
(function price (i64) i64 :merge (min old new))
(ruleset probe) (ruleset update) (ruleset together)
(rule ((Seed x)) ((set (price x) 10)) :ruleset update)
(rule ((= v (price 7))) ((Seen v)) :ruleset probe)
(rule ((Seed x)) ((L x)) :ruleset together)
(rule ((L x)) ((R x)) :ruleset together)
(Seed 7) (set (price 7) 20)
(run-schedule (run probe) (run update) (run probe) (run together) (run together))
"""


def control(a):
    with TemporaryDirectory() as temp:
        root = Path(temp)
        src = root / "source.egg"
        src.write_text(SOURCE)
        build = root / "compiled"
        subprocess.run(
            [a.compiler, "compile", "--source", src, "--output", build],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        ir = build / "program.json"
        sha = hashlib.sha256(ir.read_bytes()).hexdigest()
        recipe = json.loads(ir.read_bytes())["recipe"]
        outputs = json.loads(
            subprocess.check_output([a.runtime, "receipt-contract", ir])
        )["rules"]
        roles = {
            recipe["tables"][v["table"]]["name"]: (rid, int(op))
            for rid, r in enumerate(outputs)
            for op, v in r["outputs"].items()
        }
        result = []
        with subprocess.Popen(
            [a.runtime, "online-ccp-v0.1", ir, "-", "audit", "--ept"],
            stdin=-1,
            stdout=-1,
        ) as p:
            c = Client(p, 4, sha)
            try:
                while True:
                    h = json.loads(p.stdout.readline())
                    if "role" in h:
                        break
                    memory_frame(p.stdout, h)
                    if len(read_repairs(p.stdout, h)[0]):
                        raise ValueError("unexpected repair")
                    if h.get("final_publication"):
                        continue
                    run = c.run = h["run"]
                    c.epoch = h["epoch"]
                    archive = root / "tape"
                    archive.write_text(
                        json.dumps(
                            {
                                "schema": "cell-token-replay/v2",
                                "program_sha256": sha,
                                "requests": list(c.offline_tape(run - 1)),
                                "repair_events": [],
                            }
                        )
                    )
                    qs = json.loads(
                        subprocess.check_output(
                            [
                                a.runtime,
                                "replay",
                                ir,
                                archive,
                                "audit",
                                str(run - 1),
                                "--audit-next-proofs",
                            ]
                        )
                    )
                    items = [from_q(q) for q in qs]
                    if run == 1:
                        (old,) = items
                    if run == 3:
                        items = [old, *items]
                    if run == 4:
                        (anchor,) = items
                        assert anchor.rule == roles["L"][0]
                        items.append(
                            Cell(roles["R"][0], ((c.paid + 1, roles["L"][1], c.epoch),))
                        )
                    replies = submit(c, items, 16)
                    for item, (uid, status, *_) in zip(items, replies, strict=True):
                        result.append(
                            {
                                "run": run,
                                "epoch": c.epoch,
                                "uid": uid,
                                "rule": item.rule,
                                "refs": item.refs,
                                "status": STATUS[status],
                            }
                        )
                    c.seal()
                archive.write_text(
                    json.dumps(
                        {
                            "schema": "cell-token-replay/v2",
                            "program_sha256": sha,
                            "requests": list(c.offline_tape(run)),
                            "repair_events": [],
                        }
                    )
                )
                rep = json.loads(
                    subprocess.check_output(
                        [a.runtime, "replay", ir, archive, "audit", "--ept-origins"]
                    )
                )
                assert rep["state_sha"] == h["state_sha"]
                for row in result:
                    row["gain"] = dict(rep["ept"]["origins"]).get(row["uid"], 0)
                    row["credit"] = labels(
                        row["status"], None, None, row["gain"], False
                    )
            finally:
                p.stdin.close()
                c.close()
        (a.out / "port-controls.json").write_text(json.dumps(result, indent=2) + "\n")
        assert [r["status"] for r in result if r["run"] == 3] == ["version", "accepted"]
        assert [r["status"] for r in result if r["run"] == 4] == [
            "accepted",
            "pending_port",
        ]
        assert any(
            r["run"] == 5 and r["rule"] == roles["R"][0] and r["gain"] for r in result
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for key in ("compiler", "runtime", "out"):
        p.add_argument("--" + key, type=Path, required=True)
    control(p.parse_args())

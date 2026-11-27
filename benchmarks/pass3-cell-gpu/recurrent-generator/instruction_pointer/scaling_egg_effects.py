"""Revalidate historical same-key suggestions on their exact current training snapshot."""

import json
import os
import pickle
import random
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path

import torch

from binding_egg import unpack
from ccp_v01 import Client
from cell_kv_runtime import Instances
from cell_kv_world import World
from competition_egg import egg
from credit_scale_buffer import submit
from discrete_cells import from_q
from discrete_draft import Cell
from int_parameters import digest, encode
from joint_cell_corpus import folder, read_rows
from partner_index_worlds import args
from prefix_train import make
from rule_publication import publication_observer, read_rule_frame
from scaling_archive import directory


def fork(a, w, ir_sha, s, t, export):
    receipts = defaultdict(list)
    for r, epoch, tid, refs, reply in s["request_receipts"]:
        receipts[r].append((epoch, Cell(tid, refs), reply))
    mem = Instances(w, True)
    reached = False
    trace = []
    reply = None
    cmd = [
        a.runtime_binary,
        "online-ccp-v0.1",
        w.dir / "program.json",
        "-",
        "audit",
        "--export",
        export,
        "--ept-origins",
    ]
    with (
        publication_observer(True) as (reader, _, env),
        subprocess.Popen(cmd, stdin=-1, stdout=-1, env=env) as proc,
    ):
        client = Client(proc, 512, ir_sha)
        try:
            for line in iter(proc.stdout.readline, b""):
                f = json.loads(line)
                if "role" in f:
                    break
                unpack(proc.stdout, f)
                f["rule_state"], f["check_dirty"] = read_rule_frame(reader, f)
                if reached:
                    trace.append(
                        {
                            k: f[k]
                            for k in (
                                "run",
                                "epoch",
                                "rules",
                                "rule_state",
                                "updates",
                                "retired",
                                "accepted",
                            )
                        }
                    )
                if f.get("final_publication"):
                    continue
                client.run, client.epoch = f["run"], f["epoch"]
                if not reached:
                    mem.update(f)
                    replay = receipts.pop(client.run, [])
                    actual = submit(client, [x[1] for x in replay], 16)
                    for (epoch, cell, expected), out in zip(
                        replay, actual, strict=True
                    ):
                        if epoch != client.epoch or tuple(out) != expected:
                            raise ValueError(
                                "teacher prefix disagrees with native execution"
                            )
                        mem.acknowledge(client, cell.rule, cell.refs, out)
                        if not out[1]:
                            mem.begin(out[0], cell.rule, cell.refs)
                    if client.run == s["run"]:
                        if receipts or mem.snapshot(w, f) != s:
                            raise ValueError(
                                "historical target reached a different decision state"
                            )
                        reached = True
                        if t is not None:
                            [reply] = submit(client, [Cell(*t)], 1)
                client.seal()
            if proc.wait() or not reached:
                raise ValueError("counterfactual did not run to schedule end")
        finally:
            client.close()
    graph = json.loads(export.read_text())
    rows = frozenset(map(encode, graph["rows"]))
    if len(rows) != len(graph["rows"]):
        raise ValueError("duplicate exported rows")
    return (
        rows,
        digest([f["state_sha"], graph["anchors"], trace]),
        reply,
        0 if reply is None else dict(f["ept"]["origins"]).get(reply[0], 0),
    )


def collect(a):
    # Only the EggCC training program is opened.
    d = directory(a)
    p = Path(os.environ["ARTIFACT_ROOT"]) / "address-audit-1126/probes/same-key/fact"
    names = json.loads((p / "requests.json").read_text())
    verdicts = json.loads((p / "verdicts.json").read_text())
    tape = json.loads((a.data / "fact/tape.json").read_text())
    assert names["program_sha256"] == tape["program_sha256"]
    orig = {q["token"]: from_q(q) for q in tape["requests"]}
    offered = defaultdict(set)
    for q, (r, (uid, _, _), owner, reason) in zip(
        names["requests"], verdicts, strict=True
    ):
        if reason == "match" and owner == uid:
            x, y = orig[uid], from_q(q)
            assert q["run"] == r and x.rule == y.rule
            offered[r, (x.rule, x.refs)].add((y.rule, y.refs))
    w = World(egg(a, "fact")[0], make(a, "rel").actor, sides="", entry_table=None)
    rng = random.Random(18017)
    available = []
    for s, targets in read_rows(folder(a) / "fact-teacher.pkl.gz"):
        supported = {p[0] for p in s["ports"]}
        paired = {
            t: sorted(
                v for v in offered[s["run"], t] if all(ref in supported for ref in v[1])
            )
            for t in targets
        }
        paired = {t: vs for t, vs in paired.items() if vs}
        if paired:
            available.append((s, paired))
    rng.shuffle(available)
    path = d / "egg-fork-effects.jsonl"
    done = (
        {r["state"] for r in map(json.loads, path.read_text().splitlines())}
        if path.exists()
        else set()
    )
    with tempfile.TemporaryDirectory() as tmp, path.open("a", buffering=1) as sink:
        for s, paired in available[:32]:
            sh = digest(s)
            if sh in done:
                continue
            export = Path(tmp) / "rows.json"
            base, *_ = fork(a, w, names["program_sha256"], s, None, export)
            ts = sorted({t for z, others in paired.items() for t in (z, *others[:3])})
            evidence = []
            for t in ts:
                actual, signature, rep, ops = fork(
                    a, w, names["program_sha256"], s, t, export
                )
                extra, lost = actual - base, base - actual
                proven = rep[1] == 0 and ops > 0 and bool(extra) and not lost
                evidence.append(
                    [
                        t,
                        rep,
                        ops,
                        len(extra),
                        len(lost),
                        digest(sorted(extra)),
                        signature if proven else None,
                    ]
                )
            sink.write(
                json.dumps(
                    {
                        "program": names["program_sha256"],
                        "state": sh,
                        "run": s["run"],
                        "tokens": evidence,
                    },
                    separators=(",", ":"),
                )
                + "\n"
            )
    combined = {}
    for row in map(json.loads, path.read_text().splitlines()):
        group = {
            (t[0], tuple(map(tuple, t[1]))): sig
            for t, _, _, _, _, _, sig in row["tokens"]
            if sig
        }
        if group:
            combined[row["program"], row["state"]] = group
    tmp = d / "egg-fork-effects.tmp"
    tmp.write_bytes(pickle.dumps(combined))
    tmp.replace(d / "egg-fork-effects.pkl")


if __name__ == "__main__":
    torch.set_num_threads(1)
    collect(args())

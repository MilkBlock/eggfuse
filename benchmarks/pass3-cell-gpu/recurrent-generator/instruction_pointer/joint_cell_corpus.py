"""Build complete Cell targets from exact native transactions, keeping pre-Submit state."""

import gzip
import hashlib
import json
import os
import pickle
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

import torch

from binding_egg import unpack
from ccp_v01 import Client
from cell_kv_runtime import Instances
from cell_kv_world import World
from cell_transaction import STATUS
from competition_egg import egg
from credit_scale_buffer import submit
from discrete_cells import from_q
from discrete_draft import Cell
from partner_index_worlds import args
from rule_publication import publication_observer, read_rule_frame
from variable_completion import network


def folder(a):
    d = a.out / "joint-cell-pretraining"
    d.mkdir(exist_ok=True)
    return d


def write_rows(path, rows):
    with gzip.open(path, "wb", compresslevel=2) as f:
        pickle.dump(rows, f, protocol=5)


def read_rows(path):
    with gzip.open(path, "rb") as f:
        return pickle.load(f)


def collect(a, case, policy):
    d = folder(a)
    ir, _ = egg(a, case)
    net = network(a, 71)
    w = World(ir, net.actor, entry_table=None, sides="")
    prog = ir / "program.json"
    digest = hashlib.sha256(prog.read_bytes()).hexdigest()
    archive = Path(os.environ["ARTIFACT_ROOT"]) / "multi-association" / case / "audit-0"
    teacher = policy == "teacher"
    tape = json.loads(
        (
            (a.data / case / "tape.json") if teacher else archive / "accepted.json"
        ).read_text()
    )
    assert tape["program_sha256"] == digest
    events = defaultdict(list)
    if teacher:
        for q in tape["requests"]:
            events[q["run"]].append((from_q(q), q["token"], "accepted"))
    else:
        for q in json.loads((archive / "slots.json").read_text()):
            if q["uid"] is not None:
                events[q["run"]].append(
                    (
                        Cell(q["rule"], tuple(map(tuple, q["refs"]))),
                        q["uid"],
                        q["status"],
                    )
                )
    cmd = [a.runtime_binary, "online-ccp-v0.1", prog, "-", "audit", "--ept-origins"]
    if not teacher:
        cmd += ["--address-seed", str(tape["address_seed"])]
    mem = Instances(w, True)
    rows = []
    count = Counter()
    with (
        publication_observer(True) as (reader, _, env),
        subprocess.Popen(cmd, stdin=-1, stdout=-1, env=env) as proc,
    ):
        client = Client(proc, 64, digest)
        try:
            for line in iter(proc.stdout.readline, b""):
                f = json.loads(line)
                if "role" in f:
                    break
                unpack(proc.stdout, f)
                f["rule_state"], f["check_dirty"] = read_rule_frame(reader, f)
                mem.update(f)
                if f.get("final_publication"):
                    continue
                client.run = f["run"]
                client.epoch = f["epoch"]
                ev = events[client.run]
                for t in range(0, len(ev), 16):
                    block = ev[t : t + 16]
                    cells = [q[0] for q in block]
                    keep = len(mem.exposed) <= 2500 and len(mem.receipts) <= 2048
                    s = mem.snapshot(w, f) if keep else None
                    replies = submit(client, cells, 64)
                    labels = []
                    for (c, expected, why), reply in zip(block, replies, strict=True):
                        uid, status, *_ = reply
                        assert (uid, STATUS[status]) == (expected, why)
                        if keep and not status:
                            labels.append((uid, (c.rule, c.refs)))
                        mem.acknowledge(client, c.rule, c.refs, reply)
                        if not status:
                            mem.begin(uid, c.rule, c.refs)
                    count["replayed"] += len(block)
                    if labels:
                        rows.append((s, labels))
                    if not keep:
                        count["outside_size_limit"] += len(block)
                client.seal()
            assert proc.wait() == 0
        finally:
            client.close()
    ref = json.loads(
        (
            (a.data / case / "capture.json") if teacher else archive / "result.json"
        ).read_text()
    )
    assert f["state_sha"] == ref["state_sha" if teacher else "graph"]
    effects = Counter()
    for uid, v in f["ept"]["origins"]:
        effects[uid] += v
    result = []
    for s, labels in rows:
        valid = {p[0]: p[3] for p in s["ports"]}
        targets = []
        for uid, (rid, refs) in labels:
            if effects[uid] > 0:
                assert (
                    rid in s["menu"]
                    and len(refs) == len(w.roles[rid])
                    and all(
                        valid[r] == t for r, t in zip(refs, w.roles[rid], strict=True)
                    )
                )
                targets.append((rid, refs))
        if targets:
            result.append((s, targets))
    count.update(states=len(result), targets=sum(len(ts) for _, ts in result))
    write_rows(d / f"{case}-{policy}.pkl.gz", result)
    (d / f"corpus-{case}-{policy}.json").write_text(
        json.dumps(dict(counts=count, graph=f["state_sha"], program=digest))
    )
    print(case, policy, count, flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        a = args()
        for policy in ("teacher", "autonomous"):
            collect(a, os.environ["TR_CASE"], policy)

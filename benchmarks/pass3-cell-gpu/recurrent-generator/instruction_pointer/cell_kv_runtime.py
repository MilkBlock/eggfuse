"""Logical Cell ownership over actual CCP publications; offline labels never enter free draws."""

import hashlib
import json
import os
import subprocess
from collections import Counter, defaultdict
from time import perf_counter

import numpy as np

from binding_egg import unpack
from ccp_v01 import Client
from completion_context import read
from credit_scale_buffer import submit
from discrete_draft import Cell


class Instances:
    def __init__(self, w):
        self.world = w
        self.live = {}
        self.exposed = {}
        self.wait_exports = {}
        self.completed = set()
        self.instances = {}
        self.owned = {}
        self.pins = {}

    def update(self, f):
        for a in f["retired"]:
            key = a["token"], a["op"]
            self.live.pop(key, None)
            self.exposed.pop(key, None)
        for a, r in f["updates"]:
            key = (a["token"], a["op"])
            self.live[key] = r
            owner, step = self.owned.get(key[0], (key[0], 0))
            tid = self.instances.get(owner, (-1, ()))[0]
            if tid < self.world.primitives or step in (
                0,
                len(self.world.layouts[tid]) - 1,
            ):
                self.exposed[key] = None
            if key in self.wait_exports:
                self.completed.add(self.wait_exports.pop(key))
            if key[0] in self.owned:
                self.pins.setdefault(key, r["version"])

    def begin(self, uid, template, refs):
        self.instances[uid] = (template, tuple(refs))
        self.owned[uid] = (uid, 0)

    def snapshot(self, w, f):
        ports = []
        for uid, op in self.exposed:
            r = self.live[uid, op]
            owner, step = self.owned.get(uid, (uid, 0))
            tid, parents = self.instances.get(owner, (-1, ()))
            ports.append(
                (
                    (uid, op, r["version"]),
                    owner,
                    tid,
                    r["table"],
                    tuple(r["hashes"]),
                    r["forwarded"],
                    parents,
                )
            )
        # Addresses are carried for emission. Tensor order has no positional ID embedding.
        return dict(
            ports=ports,
            menu=w.menu(dict(f["rules"])),
            epoch=f["epoch"],
            run=f["run"],
            response=(len(f["accepted"]), len(f["updates"]), len(f["retired"])),
        )

    def suffix(self, w, client, scheduled, pending, stats):
        remaining = []
        for owner, tid, uids in pending:
            j = len(uids)
            rid, _, wires = w.layouts[tid][j]
            if rid not in scheduled:
                remaining.append((owner, tid, uids))
                continue
            refs = []
            for prev, op in wires:
                key = uids[prev], op
                rec = self.live.get(key)
                if rec is None or rec["version"] != self.pins.get(key):
                    break
                refs.append((*key, rec["version"]))
            if len(refs) != len(wires):
                remaining.append((owner, tid, uids))
                continue
            uid, status, *_ = submit(client, [Cell(rid, tuple(refs))], 32)[0]
            stats["paid"] += 1
            stats["internal"] += 1
            if status != 0:
                stats["higher_rejected"] += 1
                continue
            self.owned[uid] = (owner, j)
            if j + 1 == len(w.layouts[tid]):
                stats["higher_tail_accepted"] += 1
                self.wait_exports[uid, w.export_pc[tid]] = owner
            else:
                remaining.append((owner, tid, uids + [uid]))
        return remaining


def logical_rows(graph):
    # These test programs use relation rows with scalar arguments and an implicit
    # relation witness. The canonical reference digest is also reported independently.
    return {
        (r["table"], tuple(v["value"] for v in r["values"] if "value" in v))
        for r in graph["rows"]
        if not r["subsumed"] and r["table"] not in ("Seed", "Permit", "Noise")
    }


def teacher_labels(w, requests):
    """Check every internal named producer/op against the actual later consuming request."""
    by_parent = defaultdict(list)
    for q in requests:
        for p in q["parents"]:
            by_parent[p["address"]["token"]].append(q)
    paths = {}
    for q in requests:
        for tid in range(w.primitives, len(w.layouts)):
            if q["rule"] != w.layouts[tid][0][0]:
                continue
            chain = [q]
            for rid, _, wires in w.layouts[tid][1:]:
                expected = [
                    {"token": chain[prev]["token"], "op": op} for prev, op in wires
                ]
                prod = chain[wires[0][0]]
                hits = [
                    x
                    for x in by_parent[prod["token"]]
                    if x["rule"] == rid
                    and [p["address"] for p in x["parents"]] == expected
                    and all(x["run"] > chain[prev]["run"] for prev, _ in wires)
                ]
                if len(hits) != 1:
                    break
                chain += hits
            if len(chain) == len(w.layouts[tid]):
                paths[q["token"]] = tid, [x["token"] for x in chain]
    return paths


def native(a, w, *, teacher=None, policy=None, seed=0, slots=6, receipt_log=None, branch=None, reference=None):
    offline = teacher is not None
    if offline == (policy is not None):
        raise ValueError("choose offline replay or independent policy")
    if branch is not None and not offline:
        raise ValueError("counterfactual replay requires an offline prefix")
    witnessed = False
    branch_owners = set()
    rows = []
    refs_of = lambda q: tuple(
        (p["address"]["token"], p["address"]["op"], p["version"]) for p in q["parents"]
    )
    if offline:
        tape = read(w.dir / "teacher.json")["requests"]
        paths = teacher_labels(w, tape)
        roots = {layout[0][0] for layout in w.layouts[w.primitives:]}
        if set(paths) != {q["token"] for q in tape if q["rule"] in roots}:
            raise ValueError("incomplete Higher witness in the controlled corpus")
        grouped = defaultdict(list)
        for q in tape:
            grouped[q["run"]].append(q)
        owners = {}
        for owner, (tid, chain) in paths.items():
            if teacher == "higher":
                owners.update((uid, (owner, tid, j)) for j, uid in enumerate(chain))
    export = a.out / f"kv-export-{os.getpid()}.json"
    ir = w.dir / "program.json"
    cmd = [
        a.runtime_binary,
        "online-ccp-v0.1",
        ir,
        "-",
        "audit",
        "--export",
        export,
        "--ept",
    ]
    if not offline:
        cmd += ["--address-seed", str(seed * 11 + 513)]
    digest = hashlib.sha256(ir.read_bytes()).hexdigest()
    rng = np.random.default_rng(seed)
    mem = Instances(w)
    stats = Counter()
    pending = []
    start = perf_counter()
    if policy is not None:
        policy.prepare(w)
    with subprocess.Popen(cmd, stdin=-1, stdout=-1) as proc:
        client = Client(proc, 64, digest)
        try:
            for line in iter(proc.stdout.readline, b""):
                f = json.loads(line)
                if "role" in f:
                    break
                unpack(proc.stdout, f)
                mem.update(f)
                if f.get("final_publication"):
                    continue
                client.run = f["run"]
                client.epoch = f["epoch"]
                state = mem.snapshot(w, f)
                if offline and (branch is None or f["run"] < branch[0]["run"]):
                    valid = {p[0] for p in state["ports"]}
                    targets = []
                    req = grouped[f["run"]]
                    for q in req:
                        refs = refs_of(q)
                        if all(ref in valid for ref in refs):
                            targets.append((q["rule"], refs))
                            if q["token"] in paths:
                                targets.append((paths[q["token"]][0], refs))
                    if targets:
                        rows.append((state, targets))
                    replies = submit(
                        client, [Cell(q["rule"], refs_of(q)) for q in req], 64
                    )
                    for q, (uid, status, *_) in zip(req, replies, strict=True):
                        if status or q["token"] != uid:
                            raise ValueError(
                                ("teacher replay mismatch", uid, status, q)
                            )
                        if uid in owners:
                            owner, tid, j = owners[uid]
                            if j == 0:
                                mem.begin(owner, tid, refs_of(q))
                            else:
                                mem.owned[uid] = (owner, j)
                                if j + 1 == len(w.layouts[tid]):
                                    mem.wait_exports[uid, w.export_pc[tid]] = owner
                                for p in refs_of(q):
                                    assert mem.pins[p[:2]] == p[2]
                        else:
                            mem.begin(uid, q["rule"], refs_of(q))
                else:
                    pending = mem.suffix(w, client, dict(f["rules"]), pending, stats)
                    if branch is None:
                        decisions = policy.generate(w, state, rng, slots)
                    elif f["run"] == branch[0]["run"]:
                        if state != branch[0]:
                            raise ValueError("branch decision state differs from replay")
                        witnessed = True
                        decisions = branch[1]
                    else:
                        decisions = []
                    cells = [
                        Cell(w.layouts[tid][0][0], refs) for tid, refs in decisions
                    ]
                    replies = submit(client, cells, 64)
                    if receipt_log is not None:
                        receipt_log.append((state, decisions, replies))
                    stats["paid"] += len(cells)
                    stats["neural_tokens"] += len(cells)
                    for (tid, refs), (uid, status, *_) in zip(
                        decisions, replies, strict=True
                    ):
                        higher = tid >= w.primitives
                        stats["higher_selected"] += int(higher)
                        if status:
                            continue
                        mem.begin(uid, tid, refs)
                        if higher:
                            pending.append((uid, tid, [uid]))
                            if branch is not None:
                                branch_owners.add(uid)
                            stats["higher_opened"] += 1
                        if tid in w.finals and any(
                            mem.instances.get(mem.owned.get(ref[0], (-1, 0))[0], (-1,))[
                                0
                            ]
                            >= w.primitives
                            for ref in refs
                        ):
                            stats["accepted_consumer_of_higher"] += 1
                client.seal()
            if proc.wait() != 0 or "role" not in f:
                raise RuntimeError("native run incomplete")
        finally:
            client.close()
    elapsed = perf_counter() - start
    if branch is not None and not witnessed:
        raise ValueError("unreached branch")
    if offline and branch is None:
        assert f["state_sha"] == read(w.dir / "capture.json")["state_sha"]
        if teacher == "higher":
            assert mem.completed == set(paths)
        return rows
    if branch is not None:
        stats["branch_higher_completed"] = len(branch_owners & mem.completed)
    stats["higher_completed"] = len(mem.completed)
    stats["awaiting_final_publication"] = len(mem.wait_exports)
    if reference is None:
        actual = logical_rows(read(export))
        ref = logical_rows(read(w.dir / "reference.json"))
    else:
        actual, ref = reference(read(export))
    if actual - ref:
        raise ValueError("unexpected logical facts")
    ops = sum(f["ept"]["signed_external"]) + sum(f["ept"]["signed_internal"])
    return dict(
        covered=len(actual),
        reference=len(ref),
        coverage=len(actual) / len(ref),
        ops=ops,
        ept=ops / max(1, stats["paid"]),
        eps=ops / elapsed,
        wall=elapsed,
        graph=f["state_sha"],
        reference_graph=f["state_sha"] == read(w.dir / "capture.json")["state_sha"],
        pending=len(pending),
        stats=dict(stats),
        receipts=f["counts"],
        facts=sorted(actual),
    )

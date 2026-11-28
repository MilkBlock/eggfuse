"""Logical Cell ownership over actual CCP publications; offline labels never enter free draws."""

import hashlib
import json
import os
import subprocess
import threading
from collections import Counter, defaultdict
from contextlib import nullcontext
from time import perf_counter

import numpy as np

from binding_egg import unpack
from ccp_v01 import Client
from completion_context import read
from credit_scale_buffer import submit
from discrete_draft import Cell
from rule_publication import publication_observer, read_rule_frame


class Instances:
    def __init__(self, w, receipt_memory=False):
        self.world = w
        self.receipts = [] if receipt_memory else None
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

    def acknowledge(self, client, tid, refs, reply):
        if self.receipts is not None:
            self.receipts.append((client.run, client.epoch, tid, tuple(refs), tuple(reply)))

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
            **({"request_receipts": tuple(self.receipts)} if self.receipts is not None else {}),
            **({"rule_state": f["rule_state"], "check_dirty": f["check_dirty"]} if "rule_state" in f else {}),
            menu=w.menu(dict(f["rules"])),
            epoch=f["epoch"],
            run=f["run"],
            response=(len(f["accepted"]), len(f["updates"]), len(f["retired"])),
        )

    def suffix(self, w, client, scheduled, pending, stats, paid_limit=None, execution_trace=None):
        remaining = []
        for owner, tid, uids in pending:
            j = len(uids)
            rid, _, wires = w.layouts[tid][j]
            if rid not in scheduled or (paid_limit is not None and stats["paid"] >= paid_limit):
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
            reply = submit(client, [Cell(rid, tuple(refs))], 32)[0]
            self.acknowledge(client, rid, refs, reply)
            uid, status, *_ = reply
            stats["paid"] += 1
            stats["internal"] += 1
            if execution_trace is not None:
                execution_trace.step(owner, j, rid, reply)
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


def native(
    a, w, *, teacher=None, policy=None, seed=0, slots=6, receipt_log=None,
    branch=None, reference=None, paid_limit=None, publication_log=None,
    diagnostic_followup=None, receipt_memory=False, submit_pages=1, rule_state=None, execution_trace=None,
):
    if rule_state is None:
        rule_state = getattr(getattr(policy, "net", None), "rule_condition", "none") != "none"
    offline = teacher is not None
    if offline == (policy is not None):
        raise ValueError("choose offline replay or independent policy")
    if branch is not None and not offline:
        raise ValueError("counterfactual replay requires an offline prefix")
    if paid_limit is not None and (offline or paid_limit < 0):
        raise ValueError("paid cap requires a policy and a nonnegative budget")
    if submit_pages < 1 or (submit_pages != 1 and (offline or diagnostic_followup is not None)):
        raise ValueError("multiple pages require an independent policy")
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
    export = getattr(a, "native_export_dir", a.out) / f"kv-export-{os.getpid()}-{threading.get_ident()}.json"
    ir = w.dir / "program.json"
    cmd = [
        a.runtime_binary,
        "online-ccp-v0.1",
        ir,
        "-",
        "audit",
        "--export",
        export,
        "--ept-origins" if execution_trace is not None else "--ept",
    ]
    if not offline:
        cmd += ["--address-seed", str(seed * 11 + 513)]
    digest = hashlib.sha256(ir.read_bytes()).hexdigest()
    rng = np.random.default_rng(seed)
    mem = Instances(w, receipt_memory)
    stats = Counter()
    pending = []
    start = perf_counter()
    if policy is not None:
        policy.prepare(w)
    if execution_trace is not None and (offline or not rule_state):
        raise ValueError("attribution requires a signed, observed run")
    with (
        policy.inference_session() if hasattr(policy, "inference_session") else nullcontext(),
        publication_observer(rule_state, execution_trace is not None) as (reader, audit_path, env),
        subprocess.Popen(cmd, stdin=-1, stdout=-1, env=env) as proc,
    ):
        client = Client(proc, 64, digest)
        try:
            for line in iter(proc.stdout.readline, b""):
                f = json.loads(line)
                if "role" in f:
                    break
                unpack(proc.stdout, f, getattr(policy, "observe_native_memory", None))
                if reader is not None:
                    f["rule_state"], f["check_dirty"] = read_rule_frame(reader, f)
                mem.update(f)
                if publication_log is not None:
                    publication_log.append({k: f.get(k) for k in ("run", "epoch", "rules", "accepted", "updates", "retired", "final_publication")})
                if f.get("final_publication"):
                    continue
                if policy is not None and hasattr(policy, "observe_publication"):
                    policy.observe_publication(f)
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
                    for q, reply in zip(req, replies, strict=True):
                        uid, status, *_ = reply
                        template = owners[uid][1] if uid in owners and owners[uid][2] == 0 else q["rule"]
                        mem.acknowledge(client, template, refs_of(q), reply)
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
                    pending = mem.suffix(w, client, dict(f["rules"]), pending, stats, paid_limit, execution_trace)
                    if branch is None:
                        decisions = None
                    elif f["run"] == branch[0]["run"]:
                        if state != branch[0]:
                            raise ValueError("branch decision state differs from replay")
                        witnessed = True
                        decisions = branch[1]
                    else:
                        decisions = []
                    batches = [decisions] * submit_pages
                    if diagnostic_followup is not None and f["run"] == diagnostic_followup[0]["run"]:
                        if state != diagnostic_followup[0] or paid_limit is not None or publication_log is None:
                            raise ValueError("same-window probe requires the exact audited snapshot")
                        batches.append(diagnostic_followup[1])
                    for batch_i, decisions in enumerate(batches):
                        if batch_i or receipt_memory:
                            state = mem.snapshot(w, f)
                        if decisions is None:
                            available = slots // submit_pages + int(batch_i < slots % submit_pages)
                            if paid_limit is not None:
                                available = min(available, paid_limit - stats["paid"])
                            decisions = policy.generate(w, state, rng, available) if available else []
                            if paid_limit is not None and len(decisions) > available:
                                raise ValueError("generated page exceeded its slot budget")
                        cells = [
                            Cell(w.layouts[tid][0][0], refs) for tid, refs in decisions
                        ]
                        replies = submit(client, cells, 64)
                        if receipt_log is not None:
                            receipt_log.append((state, decisions, replies))
                        stats["paid"] += len(cells)
                        stats["neural_tokens"] += len(cells)
                        for (tid, refs), reply in zip(
                            decisions, replies, strict=True
                        ):
                            mem.acknowledge(client, tid, refs, reply)
                            uid, status, *_ = reply
                            higher = tid >= w.primitives
                            stats["higher_selected"] += int(higher)
                            if execution_trace is not None:
                                execution_trace.entry(w, state, tid, refs, reply)
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
            if execution_trace is not None:
                execution_trace.finish(f["ept"], audit_path, mem.completed)
                if hasattr(execution_trace, "response_history"):
                    execution_trace.response_history(mem.receipts)
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
        **({"completed_owners": sorted(mem.completed)} if publication_log is not None else {}),
        stats=dict(stats),
        transport=dict(client.costs),
        native_verify_seconds=f.get("verify_seconds"),
        receipts=f["counts"],
        facts=sorted(actual),
    )

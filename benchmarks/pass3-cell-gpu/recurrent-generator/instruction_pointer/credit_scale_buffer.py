"""Native CCP collection with offline exact forks and independent resident Metal pages."""

import gzip
import hashlib
import json
import os
import random
import subprocess
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

import numpy as np
import torch

from ccp_v01 import Client, offline_repairs, read_repairs
from cell_transaction import memory_frame
from credit_scale_programs import directory, split_check
from discovery_sampling import Domain, encode
from discovery_states import cli, read
from discrete_cells import from_q
from query_environment import conditioned, setup


def submit(client, cells, width):
    result = []
    for start in range(0, len(cells), width):
        ops, refs = [], []
        for c in cells[start : start + width]:
            if c.higher:
                raise ValueError(
                    "primitive DAG collector cannot lower a Higher activation"
                )
            refs.extend((*ref, -1) for ref in c.refs)
            ops.append([0, 0, c.rule, -1, len(refs)])
        ticket = client.enqueue(
            np.asarray(ops), np.asarray(refs, dtype=np.int64).reshape(-1, 4)
        )
        result.extend(client.collect(ticket).rows.tolist())
    return result


class Lane:
    def __init__(self, a, idx, branch, signature):
        self.a, self.idx, self.branch, self.signature = a, idx, branch, signature
        self.program = directory(a, idx) / "program.json"
        self.program_sha = hashlib.sha256(self.program.read_bytes()).hexdigest()
        self.scratch = tempfile.TemporaryDirectory()
        self.tmp = Path(self.scratch.name)
        self.scheduler = self.tmp / "scheduler"
        self.seed = 42761 + idx * 11 + branch + getattr(a, "rollout_seed", 0)
        self.rng = np.random.default_rng(self.seed)
        self.shuffle = random.Random(73255 + 31 * idx + branch)
        self.m = conditioned(a, self.program.parent, self.scheduler)
        if self.m.menu:
            raise ValueError("training family must contain only primitive recipes")
        cfg = SimpleNamespace(**(vars(a) | {"out": a.checkpoint.parent}))
        self.page = setup(cfg, self.m, a.checkpoint.stem, a.cap)[2]
        if getattr(a, "record_slot_attempts", False):
            from throughput_slots import SlotLog, instrument

            instrument(self.page, SlotLog(retain_page=True))
        self.proc = subprocess.Popen(
            [a.runtime_binary, "online-ccp-v0.1", self.program, "-", "audit", "--ept"],
            stdin=-1,
            stdout=-1,
            env=dict(
                os.environ,
                EGGFUSE_QUERY_OBSERVER=str(self.scheduler),
                EGGFUSE_ADMISSION_OBSERVER=str(self.tmp / "admission.csv"),
            ),
        )
        self.client = Client(self.proc, 512, self.program_sha)
        self.events = []
        self.repairs = []
        self.cost = Counter()
        self.done = False
        self.start = perf_counter()

    def replay(self, rows, *args):
        p = self.tmp / "fork.json"
        p.write_text(
            json.dumps(
                {
                    "schema": "cell-token-replay/v2",
                    "program_sha256": self.program_sha,
                    "requests": rows,
                    "repair_events": list(offline_repairs(self.repairs)),
                }
            )
        )
        return json.loads(
            subprocess.check_output(
                [
                    self.a.runtime_binary,
                    "replay",
                    self.program,
                    p,
                    "audit",
                    *map(str, args),
                ]
            )
        )

    def advance(self):
        while True:
            h = json.loads(self.proc.stdout.readline())
            if "role" in h:
                self.terminal = h
                self.done = True
                return
            rows, hashes, ret, accepted = memory_frame(self.proc.stdout, h)
            desc, ops = read_repairs(self.proc.stdout, h)
            if len(desc):
                self.repairs.append((desc, ops))
            if h.get("final_publication"):
                continue
            self.client.epoch = h["epoch"]
            self.client.run = h["run"]
            f = {
                "run": h["run"],
                "epoch": h["epoch"],
                "rules": h["rules"],
                "accepted": accepted.tolist(),
                "retired": [{"token": int(t), "op": int(o)} for t, o in ret],
                "updates": [],
            }
            i = 0
            for t, o, tab, v, fw, end in rows.tolist():
                f["updates"].append(
                    [
                        {"token": t, "op": o},
                        {
                            "table": tab,
                            "version": v,
                            "forwarded": bool(fw),
                            "hashes": hashes[i:end].tolist(),
                        },
                    ]
                )
                i = end
            self.frame = f
            return

    def finish_run(self, cells):
        r = self.client.run
        prefix = list(self.client.offline_tape(r - 1))
        start = perf_counter()
        replies = submit(self.client, cells, 128)
        issue_seconds = perf_counter() - start
        accepted_tape = list(self.client.offline_tape(r))
        tick = perf_counter()
        base = self.replay(accepted_tape, r, "--ept-origins")
        exact = self.replay(prefix, r - 1, "--audit-next-proofs")
        prior = self.replay(prefix, r - 1)
        used = set(cells)
        uid = self.client.paid + 1
        extra = [
            dict(q, token=uid + i) for i, q in enumerate(exact) if from_q(q) not in used
        ]
        trial = (
            self.replay(accepted_tape + extra, r, "--ept-origins") if extra else base
        )
        before = dict(base["ept"]["origins"])
        after = dict(trial["ept"]["origins"])
        stable = all(
            before.get(q["token"], 0) == after.get(q["token"], 0) for q in accepted_tape
        )
        gains = [
            (encode(from_q(q)), after[q["token"]])
            for q in extra
            if stable and after.get(q["token"], 0)
        ]
        effects = lambda rep: (
            sum(rep["ept"]["signed_external"]) + sum(rep["ept"]["signed_internal"])
        )
        if stable and sum(v for _, v in gains) != effects(trial) - effects(base):
            raise ValueError("overlapping omission credit")
        self.cost["audit_seconds"] += perf_counter() - tick
        # Only the explicitly assisted training trajectories receive oracle proposals.
        supplemental = list(map(from_q, exact))
        if self.branch == 1:
            self.shuffle.shuffle(supplemental)
            supplemental = supplemental[
                : self.shuffle.randint(
                    len(supplemental) // 3,
                    max(len(supplemental) // 3, len(supplemental) * 3 // 4),
                )
            ]
        if self.branch == 2 or (self.branch == 1 and r % 3 == 0):
            supplemental = []
        rand = []
        if self.branch == 1:
            domain = Domain(self.m)
            rand = list(domain.draw("factored", self.shuffle, min(8, domain.size)))
        assist = rand + supplemental
        assist_replies = submit(
            self.client,
            assist,
            self.shuffle.choice((32, 64, 128)) if self.branch else 128,
        )
        event = {
            "frame": self.frame,
            "semantic_state": prior["state_sha"],
            "context": self.context,
            "generated": [encode(c) for c in cells],
            "response": replies,
            "signed_gain": [before.get(v[0], 0) for v in replies],
            "omitted": gains,
            "stable": stable,
            "known_bindings": len(exact),
            "accepted_effects": base["ept"]["signed_external"],
            "random_count": len(rand),
            "assisted": [encode(c) for c in assist],
            "assisted_response": assist_replies,
            "issue_seconds": issue_seconds,
        }
        if observer := getattr(self.page, "slot_observer", None):
            slots = observer.last_page
            if slots is None or sum(raw[1] == 0 for raw in slots) != len(replies):
                raise ValueError("slot trace does not match submitted page")
            event["slot_attempts"] = slots
            event["attempt_schema"] = "named-slot-attempt/v1"
            # A typed lookup failure is observable. No counterfactual value or abandonment label.
            event["unsubmitted_credit_mask"] = False
            observer.last_page = None
        self.events.append(event)
        self.client.seal()
        self.advance()

    def close(self):
        try:
            if not self.done:
                self.proc.kill()
            self.proc.stdin.close()
            self.proc.wait()
        finally:
            self.client.close()
            self.m.close_observer()
            self.scratch.cleanup()

    def save(self):
        self.proc.wait(timeout=20)
        # This observer is written inside native admission, independently of the
        # generation observer. Neither stream feeds proposals back to the actor.
        admissions = [
            list(map(int, line.split(",")))
            for line in (self.tmp / "admission.csv").read_text().splitlines()
        ]
        signed = list(self.client.offline_tape(self.client.run))
        final = self.replay(signed, "--ept-origins")
        assert (
            final["state_sha"] == self.terminal["state_sha"]
            and len(signed) == final["counts"]["accepted"]
        )
        obj = {
            "idx": self.idx,
            "rollout_seed": self.seed,
            "slot_budget": self.a.cap,
            "branch": self.branch,
            "signature": self.signature,
            "program": self.program_sha,
            "checkpoint": self.a.policy_sha,
            "events": self.events,
            "admissions": admissions,
            "origins": final["ept"]["origins"],
            "repair_events": list(offline_repairs(self.repairs)),
            "signed_external": final["ept"]["signed_external"],
            "terminal": final["state_sha"],
            "scheduler": [
                json.loads(s) for s in self.scheduler.read_text().splitlines()
            ],
            "elapsed": perf_counter() - self.start,
            "device": dict(self.page.count),
            "cost": dict(self.cost),
            "ccp": dict(self.client.costs),
        }
        path = shard(self.a, self.idx, self.branch)
        with gzip.open(path.with_suffix(".tmp"), "wt", compresslevel=1) as f:
            json.dump(obj, f, separators=(",", ":"))
        path.with_suffix(".tmp").replace(path)


def shard(a, i, b):
    seed = getattr(a, "rollout_seed", 0)
    suffix = f"-s{seed}" if seed else ""
    if getattr(a, "record_slot_attempts", False):
        suffix += "-slots"
    return a.out / "buffer" / f"{i:04d}-{b}-{a.policy_sha[:12]}{suffix}.json.gz"


@torch.no_grad()
def collect(a):
    (a.out / "buffer").mkdir(parents=True, exist_ok=True)
    a.policy_sha = hashlib.sha256(a.checkpoint.read_bytes()).hexdigest()
    bank = read(a.previous / "corpus.json")
    if (a.out / "novel/corpus.json").exists():
        bank += read(a.out / "novel/corpus.json")
    held = {p["signature"] for p in read(a.previous / "held" / "corpus.json")}
    if len({p["signature"] for p in bank}) != len(bank) or any(
        p["signature"] in held for p in bank
    ):
        raise ValueError("training DAG split overlap")
    split_check(a.previous, [v["id"] for v in bank])
    todo = [
        (a, v["id"], b, v["signature"])
        for v in bank
        if a.first <= v["id"] < a.stop
        for b in a.branches
        if not shard(a, v["id"], b).exists()
    ]
    if not todo:
        return
    totals = Counter()
    started = perf_counter()
    with ThreadPoolExecutor(max_workers=a.lanes) as pool:
        for first in range(0, len(todo), a.lanes):
            lanes = []
            try:
                for args in todo[first : first + a.lanes]:
                    lanes.append(Lane(*args))
                list(pool.map(lambda l: l.advance(), lanes))
                while active := [l for l in lanes if not l.done]:
                    wave_start = perf_counter()
                    raw = []
                    for l in active:
                        l.m.update(l.frame)
                        l.context = l.m.context().tolist()
                        raw.append(l.page.device_sample(l.m, l.rng))
                    reply = torch.cat(raw).cpu()
                    totals["batch_generation_and_memory_seconds"] += (
                        perf_counter() - wave_start
                    )
                    totals["shared_readbacks"] += 1
                    totals["program_pages"] += len(active)
                    chunks = reply.split([v.numel() for v in raw])
                    batches = []
                    for l, x in zip(active, chunks, strict=True):
                        stats = Counter()
                        batches.append([v.cell for v in l.page.decode_sample(x, stats)])
                        l.cost.update(stats)
                        l.cost["shared_downloads_fraction"] += 1 / len(active)
                        l.cost["download_bytes"] += x.numel() * x.element_size()
                        l.cost["gpu_slots"] += l.page.cap
                    list(
                        pool.map(
                            lambda args: args[0].finish_run(args[1]),
                            zip(active, batches, strict=True),
                        )
                    )
                for l in lanes:
                    l.save()
            finally:
                for lane in lanes:
                    lane.close()
            print(
                "stored",
                first + len(lanes),
                "of",
                len(todo),
                round(perf_counter() - started, 2),
                flush=True,
            )
    metrics = dict(totals, episodes=len(todo), wall=perf_counter() - started)
    branches = "-".join(map(str, a.branches))
    trace_suffix = "-slots" if getattr(a, "record_slot_attempts", False) else ""
    metric_path = (
        a.out
        / f"collection-{a.first}-{a.stop}-b{branches}-{a.policy_sha[:12]}{trace_suffix}.json"
    )
    metric_path.write_text(json.dumps(metrics) + "\n")


if __name__ == "__main__":
    p = cli()
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--first", type=int, default=0)
    p.add_argument("--stop", type=int, default=128)
    p.add_argument("--record-slot-attempts", action="store_true")
    p.add_argument("--rollout-seed", type=int, default=0)
    p.add_argument("--cap", type=int, default=160)
    p.add_argument("--lanes", type=int, default=4)
    p.add_argument("--branches", type=int, nargs="+", default=[0, 1])
    torch.set_num_threads(1)
    collect(p.parse_args())

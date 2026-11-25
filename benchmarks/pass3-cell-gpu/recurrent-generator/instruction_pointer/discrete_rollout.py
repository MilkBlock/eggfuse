"""Independent native CCP runs, sparse learned address reads, editable drafts and paid receipts."""

import argparse
import hashlib
import itertools
import json
from collections import deque
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import numpy as np
import torch

from discrete_cells import setup
from discrete_draft import Local, plan
from discrete_editor import sampler
from discrete_study import load, save
from latent_cell_flow import ZERO
from latent_egg_higher import EggHigher
from recursive_coverage import Target, snapshot
from recursive_train import folder, read
from transaction_native import execute


class Policy:
    resume_programs = EggHigher.resume_programs

    def __init__(self, m, marks, nets, arm, steps, seed, waves):
        self.m = m
        self.confirmed = m.pub
        self.marks = marks
        self.nets = nets
        self.arm = arm
        self.steps = steps
        self.rng = np.random.default_rng(seed)
        self.waves = waves
        self.waiting = []
        self.events = deque()
        self.revisit = deque()
        self.turn = 0
        self.partial = []

    def issue(self, items, txn, stats):
        ready = [item for item in items if not any(isinstance(p, Local) for p in item.cell.refs)]
        replies = self.send(ready, txn, stats)
        owners = {item.uid: int(row[0]) for item, row in zip(ready, replies, strict=True) if row[1] == 0}
        dependent = [item for item in items if any(isinstance(p, Local) for p in item.cell.refs)]
        if dependent:
            self.partial.append((dependent, owners, {}))
        return {item.uid: row for item, row in zip(ready, replies, strict=True)}

    def resume_local(self, frame, txn, stats):
        from dataclasses import replace

        next_programs = []
        for items, owners, versions in self.partial:
            remaining = []
            for item in items:
                for ref in item.cell.refs:
                    if isinstance(ref, Local) and ref.owner in owners:
                        key = owners[ref.owner], ref.port
                        if key in self.confirmed.live:
                            versions.setdefault(key, self.confirmed.live[key][0]["version"])
            for item in items:
                refs = []
                for ref in item.cell.refs:
                    if not isinstance(ref, Local):
                        refs.append(ref)
                        continue
                    if ref.owner not in owners:
                        break
                    a = owners[ref.owner], ref.port
                    stats["local_receipt_reads"] += 1
                    if a not in self.confirmed.live:
                        break
                    version = self.confirmed.live[a][0]["version"]
                    if versions.setdefault(a, version) != version:
                        break
                    refs.append((*a, version))
                if len(refs) != len(item.cell.refs) or item.cell.rule not in dict(frame["rules"]):
                    remaining.append(item)
                    continue
                materialized = replace(item, cell=replace(item.cell, refs=tuple(refs)))
                row = self.send([materialized], txn, stats)[0]
                stats["local_issued"] += 1
                if row[1] == 0:
                    owners[item.uid] = int(row[0])
                    stats["local_accepted"] += 1
            if remaining:
                next_programs.append((remaining, owners, versions))
        self.partial = next_programs

    def send(self, items, txn, stats):
        if not items:
            return []
        if len(items) > txn.capacity:
            return np.concatenate(
                [
                    self.send(items[i : i + txn.capacity], txn, stats)
                    for i in range(0, len(items), txn.capacity)
                ]
            )
        ops = []
        refs = []
        for item in items:
            c = item.cell
            refs.extend([(*p, -1) for p in c.refs])
            ops.append([0, 0, c.rule, -1, len(refs)])
        resp = txn.collect(
            txn.enqueue(
                np.asarray(ops, np.int64),
                np.asarray(refs, np.int64).reshape(-1, 4),
                np.asarray([item.cell.observe for item in items], dtype=np.uint8),
            )
        ).rows.numpy()
        for item, row in zip(items, resp, strict=True):
            c = item.cell
            stats["selected_high"] += int(c.higher)
            if c.higher and row[1] == 0:
                self.waiting.append((self.m.menu[c.rule], c.refs, [int(row[0])], {}))
                stats["instantiated"] += 1
        return resp

    def run_snapshot(self, frame, pub, rd, model, txn, stats, deadline):
        m = self.m
        tick = perf_counter()
        rows, _, retired, _ = pub
        updates = [
            (dict(token=int(r[0]), op=int(r[1])), rd.store.visible[int(r[0]), int(r[1])]) for r in rows
        ]
        m.update(
            dict(
                updates=updates,
                retired=[dict(token=int(t), op=int(o)) for t, o in retired],
                rules=frame["rules"],
                accepted=pub[3],
            )
        )
        self.events.extend((a["token"], a["op"]) for a, _ in updates)
        stats["memory_seconds"] += perf_counter() - tick
        self.resume_programs(frame, pub, txn, stats)
        self.resume_local(frame, txn, stats)
        signed = set()
        for _ in range(self.waves) if self.waves else itertools.count():
            stats["stream_pages"] += 1
            if perf_counter() >= deadline:
                raise TimeoutError
            # FIFO new publications and round-robin old named evidence. No semantic key is used.
            queue = self.revisit if self.revisit and (self.turn % 3 == 2 or not self.events) else self.events
            self.turn += 1
            if queue:
                key = queue.popleft()
                if key in m.pub.live:
                    self.revisit.append(key)
                    m.last = key
                    m.event = m.key(key)
                    stats["event_reads"] += 1
                else:
                    m.last = None
                    m.event = ZERO
                    stats["retired_events"] += 1
            if not m.ids or self.arm == "noop":
                break
            src = []
            if self.arm not in ("empty", "supervised-empty", "mask-empty"):
                for _ in range(2):
                    c = self.marks.draw(m, self.rng, stats, prefix=plan(src))
                    if c is not None:
                        src.append(c)
            stats["draft_tokens"] += len(src)
            before = self.draft if hasattr(self, "draft") else plan(src)
            method = {"raw": None, "supervised-empty": "editor", "empty": "flow", "mask-empty": "mask"}.get(
                self.arm, self.arm
            )
            tick = perf_counter()
            after = (
                sampler(self.nets[method], self.marks, m, before, method, self.steps, self.rng, stats)
                if method
                else before
            )
            stats["sampling_seconds"] += perf_counter() - tick
            if hasattr(self, "dispatch_prefix"):
                after = self.dispatch_prefix(after, stats)
            cells = [v.cell for v in after]
            stats["final_tokens"] += len(cells)
            stats["prefinal_duplicate_excess"] += len(src) - len(set(src))
            stats["postedit_duplicate_excess"] += len(cells) - len(set(cells))
            for c in cells:
                stats["same_run_repeat_signed"] += int(c in signed)
                signed.add(c)
            if not after and not self.waves:
                stats["empty_page_stops"] += 1
                break
            resp = self.issue(after, txn, stats)
            # Record a witness only when the edited survivor was issued and accepted.
            if (
                len(src) == 2
                and src[0] == src[1]
                and cells == [src[0]]
                and after[0].uid in resp
                and resp[after[0].uid][1] == 0
            ):
                stats["deleted_twin_with_accepted_survivor"] += 1
            if len(resp):
                item = next(v for v in reversed(after) if v.uid in resp)
                c = item.cell
                m.receipt = m.graph((c.rule, c.higher)) * (1 if resp[item.uid][1] == 0 else -1)
                if hasattr(m, "observe_reply"):
                    m.observe_reply(after, resp)
                else:
                    m.state = (m.pub.total.float() / 16).asinh().tanh() + 0.1 * m.receipt
        stats["unresolved_local_requests"] = sum(len(p[0]) for p in self.partial)
        stats["never_serviced_events"] = len(self.events)
        stats["open_instances"] = len(self.waiting)


@torch.no_grad()
def run(a):
    marks, nets = load(a)
    d = folder(a.root, a.case)
    unit = read(d / "layouts.json")[0] if a.case.startswith("edit-held-") else None
    primitive_only = getattr(a, "primitive_only", False)
    t = perf_counter()
    m = setup(
        a.root, d, a.actor, None if primitive_only else unit, allow_high=unit is None and not primitive_only
    )
    root_code_only = getattr(a, "root_code_only", False)
    if root_code_only:
        m.codes = {rule: m.enc.graphs[rule] for rule in m.menu}
    static_cost = perf_counter() - t
    exclusion = set(read(a.out / "fit.json")["signatures"])
    assert not ({m.enc.cat.int_bake.key(u) for u in m.menu.values()} & exclusion), "signature leakage"
    with TemporaryDirectory(dir=a.out) as scratch:
        path = Path(scratch) / "gold.json"
        target = Target(read(d / "program.json"), snapshot(a.root, d, "reference", "-", None, path)[0])
        initial = target.match(snapshot(a.root, d, "reference", "-", 0, path)[0])
        for spec in a.arms:
            arm, n = spec.split(":")
            steps = int(n)
            # No mutable publication or stream state crosses arms.
            from latent_cell_flow import Published

            m.pub = Published(m.enc)
            m.rows.clear()
            m.index.clear()
            m.options.clear()
            m.last = None
            m.receipt = ZERO
            pol = Policy(m, marks, nets, arm, steps, a.seed, a.waves)
            row = execute(a.root, a.case, study=pol, seconds=a.seconds, series=scratch)
            end = read(Path(scratch) / (a.case + "-stream-multi") / "state.json")
            covered = sorted(target.match(end) - initial)
            wall = row["wall"] + row["runtime_setup_seconds"] + static_cost
            row.update(
                arm=arm,
                steps=steps,
                seed=a.seed,
                block=a.block,
                waves=a.waves,
                covered=len(covered),
                reference=len(target.gold) - len(initial),
                coverage_sha=hashlib.sha256(json.dumps(covered).encode()).hexdigest(),
                cold_wall=wall,
                cold_eps=row["signed_ops"] / wall,
                static_setup=static_cost,
                menu=len(m.menu),
            )
            if getattr(a, "milestones", False):
                obs = []
                tape = Path(scratch) / (a.case + "-stream-multi") / "issued.json"
                runs = {1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 16, 24, 32, 64, 128, len(row["trace"])}
                for ix, entry in enumerate(row["trace"], 1):
                    if ix not in runs:
                        continue
                    state, report = snapshot(a.root, d, "replay", tape, ix, path, ept=True)
                    gold = sorted(target.match(state) - initial)
                    eff = sum(report["ept"]["signed_external"]) + sum(report["ept"]["signed_internal"])
                    obs.append(
                        dict(
                            run=ix,
                            covered=len(gold),
                            coverage_sha=hashlib.sha256(json.dumps(gold).encode()).hexdigest(),
                            paid=entry["paid"],
                            wall=static_cost + row["runtime_setup_seconds"] + entry["elapsed"],
                            effective=eff,
                        )
                    )
                save(a.out / f"milestone-{a.case}-{arm}{n}-b{a.block}.json", obs)
            row.pop("trace", None)
            suffix = "rootonly" if root_code_only else "prim" if primitive_only else ""
            if not getattr(a, "milestones", False):
                save(a.out / f"{a.case}__{arm}{n}{suffix}_w{a.waves}_b{a.block}.json", row)
            print(a.case, spec, len(covered), row["paid"], round(wall, 2), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for k in ("root", "out", "actor"):
        p.add_argument(k, type=Path)
    p.add_argument("case")
    p.add_argument("arms", nargs="+")
    p.add_argument("--seed", type=int, default=536)
    p.add_argument("--waves", type=int, default=2)
    p.add_argument("--block", type=int, default=0)
    p.add_argument("--seconds", type=int, default=180)
    p.add_argument("--milestones", action="store_true")
    p.add_argument("--primitive-only", action="store_true")
    p.add_argument("--root-code-only", action="store_true")
    args = p.parse_args()
    torch.set_num_threads(1)
    run(args)

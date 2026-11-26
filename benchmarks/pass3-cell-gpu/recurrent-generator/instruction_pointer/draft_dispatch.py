"""Explicit draft-position selection on the existing CCP proof/publication contract."""

from time import perf_counter

import numpy as np
import torch
from torch.nn.functional import softplus

from discrete_draft import Local
from discrete_editor import features
from region_owner import Instance
from response_plan import ResponsePolicy, revise_references


def correlate(outstanding, rows):
    replies = {}
    for row in rows:
        rid = int(row[0])
        if rid not in outstanding:
            raise ValueError(f"unknown or repeated CCP request {rid}")
        item = outstanding.pop(rid)
        replies[item.uid] = row
    if outstanding:
        raise ValueError("missing CCP responses")
    return replies


def dependency_free(item):
    return all(not isinstance(ref, Local) and ref[2] >= 0 for ref in item.cell.refs)


def settle(items, replies):
    def receipt(ref):
        if isinstance(ref, Local) and ref.owner in replies:
            row = replies[ref.owner]
            return (int(row[0]) if row[1] == 0 else 0, ref.port, -1)
        return ref

    return revise_references(items, receipt)


class Dispatch(ResponsePolicy):
    def __init__(self, *args, mode):
        super().__init__(*args)
        self.mode = mode
        self.select_rng = np.random.default_rng(12011)
        self.journal = []
        self.delayed = []
        self.inference = 0.0
        self.by_run = {}
        self.receipts = []

    def dispatch_prefix(self, items, stats):
        self.journal.append(
            {
                "run": self.current,
                "rules": [i.cell.rule for i in items],
                "uids": [i.uid for i in items],
                "higher": [i.cell.higher for i in items],
            }
        )
        if self.mode == "fifo" or self.current < getattr(self, "switch_run", 0):
            issued = super().dispatch_prefix(items, stats)
        else:
            if self.mode == "page":
                selected = {i.uid for i in items}
            else:
                selected = set()
                if items:
                    start = perf_counter()
                    rates = self.nets["flow"]
                    x = features(
                        self.m.state,
                        self.m.event,
                        [self.m.embed(i.cell) for i in items],
                        1.0,
                    )
                    logits = rates(x.to(next(rates.parameters()).device))[:-1]
                    # Frozen terminal edit hazards. Draw an explicit position mask with
                    # an independent RNG so selection never consumes page-generation noise.
                    # Per-Run opcode alphabet is part of the native ABI: giving CCP
                    # an unscheduled opcode terminates the entire native process.
                    device = logits.device
                    vocabulary = torch.tensor(
                        list(self.scheduled), device=device, dtype=torch.long
                    )
                    opcodes = torch.tensor([i.cell.rule for i in items], device=device)
                    representable = torch.isin(opcodes, vocabulary)
                    if self.mode == "relative":
                        # Relative readout avoids rounding tiny terminal edit rates
                        # into indistinguishable unit probabilities. Ties survive.
                        score = -torch.logsumexp(logits[:, 1:], dim=1)
                        center = (
                            score * representable
                        ).sum() / representable.sum().clamp_min(1)
                        chosen = (representable & (score >= center)).cpu().tolist()
                    else:
                        keep = (
                            ((-softplus(logits[:, 1:]).sum(1)).exp() * representable)
                            .cpu()
                            .tolist()
                        )
                        chosen = [self.select_rng.random() < p for p in keep]
                    selected = {
                        i.uid for i, take in zip(items, chosen, strict=True) if take
                    }
                    stats["selection_seconds"] += perf_counter() - start
                    stats["selection_sites"] += len(items)
            issued = tuple(i for i in items if i.uid in selected and dependency_free(i))
            sent = {i.uid for i in issued}
            pending = tuple(i for i in items if i.uid not in sent)
            self.draft = pending if self.mode != "page" else ()
            self.page_deps = pending if self.mode == "page" else ()
            self.journal[-1]["selected"] = sorted(selected)
            stats["selected_waiting_dependency"] += len(selected - sent)
        self.journal[-1]["issued"] = [i.uid for i in issued]
        return issued

    def wire_request(self, cell):
        return 0, cell.rule, -1, [(*r, -1) for r in cell.refs]

    def issue(self, items, txn, stats):
        replies = {}
        for pos in range(0, len(items), txn.capacity):
            batch = items[pos : pos + txn.capacity]
            refs, ops = [], []
            for item in batch:
                c = item.cell
                kind, rule, pc, operands = self.wire_request(c)
                refs.extend(operands)
                ops.append([kind, 0, rule, pc, len(refs)])
            ticket = txn.enqueue(
                np.array(ops),
                np.array(refs, np.int64).reshape(-1, 4),
                np.array([i.cell.observe for i in batch], np.uint8),
            )
            flight = dict(zip(map(int, ticket.op[:, 1]), batch, strict=True))
            received = correlate(flight, txn.collect(ticket).rows.numpy())
            replies.update(received)
            for i in batch:
                row = received[i.uid]
                self.receipts.append(
                    [
                        txn.run,
                        int(row[0]),
                        i.uid,
                        i.cell.rule,
                        int(row[1]),
                        i.cell.higher,
                    ]
                )
                if i.cell.higher and row[1] == 0:
                    inst = Instance(self.m.menu[i.cell.rule], i.cell.refs)
                    self.attach(inst, int(row[0]), stats)
                    self.waiting.append(inst)
                    stats["instantiated"] += 1
        self.draft = settle(self.draft, replies)
        if deps := getattr(self, "page_deps", ()):
            self.keep_dependencies(settle(deps, replies), stats)
            self.page_deps = ()
        return replies

    def keep_dependencies(self, pending, stats):
        # A rejected local producer has no address. Its unissued descendants
        # cannot receive a future publication in a closed page.
        live = []
        failed = set()
        for item in pending:
            if any(
                (isinstance(r, Local) and r.owner in failed)
                or (not isinstance(r, Local) and r[0] == 0 and r[2] < 0)
                for r in item.cell.refs
            ):
                failed.add(item.uid)
            else:
                live.append(item)
        stats["unissued_failed_dependency"] += len(failed)
        if live:
            self.delayed.append(tuple(live))

    def resume_local(self, frame, txn, stats):
        # Each independent page has its own UID namespace. Only a previously
        # selected consumer can await publication; no semantic eligibility test.
        backlog, self.delayed = self.delayed, []
        for pending in backlog:

            def published(r):
                if (
                    not isinstance(r, Local)
                    and r[2] < 0
                    and r[0]
                    and (v := self.m.pub.live.get(r[:2]))
                ):
                    return (*r[:2], v[0]["version"])
                return r

            pending = revise_references(pending, published)
            ready = [
                i
                for i in pending
                if dependency_free(i) and i.cell.rule in self.scheduled
            ]
            replies = self.issue(ready, txn, stats)
            if ready:
                self.consume_reply(ready, replies)
            remaining = settle([i for i in pending if i.uid not in replies], replies)
            if remaining:
                self.keep_dependencies(remaining, stats)

    def run_snapshot(self, frame, *args):
        self.current = frame["run"]
        stats = args[-2]
        start = perf_counter()
        before = sum(stats[k] for k in ("sampling_seconds", "selection_seconds"))
        super().run_snapshot(frame, *args)
        self.inference += (
            sum(stats[k] for k in ("sampling_seconds", "selection_seconds")) - before
        )
        self.by_run[self.current] = self.inference
        stats["last_snapshot_seconds"] = perf_counter() - start

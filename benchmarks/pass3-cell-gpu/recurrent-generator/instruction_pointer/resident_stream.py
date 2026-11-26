"""Keep the editable tail on device across CCP responses. Stop at the next issue or Run seal."""

from time import perf_counter

import numpy as np
import torch

from discrete_draft import Cell, Item
from resident_page import Page, Slab


class StreamPage(Page):
    def __init__(self, m, marks, rates, counts):
        super().__init__(m, marks, rates, counts)
        self.identity = Slab(1, 3, torch.int32, counts)
        self.dynamic = self.upload(m.enc.actor.dynamic.weight)
        self.physical_count = 1
        self.pending = 0
        self.saved = None
        self.schedules = {}
        self.publication_events = None

    def ensure_identities(self):
        n = len(self.addresses)
        if n == self.physical_count:
            return
        self.identity.reserve(n, 3)
        lo = self.physical_count
        # The exact physical name is retained in the host store. The encoder uses
        # the low WIDTH=32 owner bits; the additional flag preserves owner-zero semantics.
        raw = [
            (owner & 0xFFFFFFFF, pc, int(owner != 0))
            for owner, pc in self.addresses[lo:]
        ]
        self.identity.data[lo:n] = self.integers(
            np.asarray(raw, np.int64).astype(np.int32)
        )
        self.physical_count = n

    def cfg(self, cap, last, seed, leap=0):
        return [
            cap,
            self.slots,
            self.pcs,
            self.tables,
            self.tabrows.data.shape[1],
            self.ownerpc.data.shape[1],
            self.len_vocab,
            last,
            seed,
            leap,
            self.width,
            2 * cap,
        ]

    def fix(self, uid, portmap):
        if self.pending:
            cfg = self.integers(self.cfg(self.pending, 0, uid))
            self.lib.fix_refs(
                self.saved,
                self.roles,
                self.meta.data,
                self.identity.data,
                portmap,
                cfg,
                threads=self.pending * self.slots,
            )

    def publication(self, frame):
        if self.publication_events is not None:
            start, end = (
                torch.mps.Event(enable_timing=True),
                torch.mps.Event(enable_timing=True),
            )
            start.record()
        super().publication(frame)
        self.ensure_identities()
        self.fix(-1, self.roles)  # unused last argument in publication mode

        if self.publication_events is not None:
            end.record()
            self.publication_events.append((start, end))

    def receipt(self, item, reply):
        if not self.pending:
            return
        owner = int(reply[0]) if reply[1] == 0 else 0
        mapping = [0] * self.pcs
        old = len(self.addresses)
        for pc in self.m.output_tables[item.cell.rule]:
            mapping[pc] = self.address((owner, pc))
        if len(self.addresses) > old:
            n = len(self.addresses)
            for slab in (self.meta, self.key, self.member, self.idvec):
                slab.reserve(n, slab.data.shape[1])
            self.meta.data[old:n, 0] = -1
            self.ensure_identities()
        self.fix(item.uid, self.integers(mapping))

    def until_boundary(self, events, stats):
        m = self.m
        cap = max(4, 1 << (self.pending + 1).bit_length())
        if self.last_rules not in self.schedules:
            enabled = torch.zeros(len(m.roles), dtype=torch.int32)
            enabled[list(self.last_rules)] = 1
            self.schedules[self.last_rules] = self.upload(enabled)
        schedule = self.schedules[self.last_rules]
        while True:
            buffers = self.scratch(cap)
            draft, embeds = buffers[:2]
            draft.zero_()
            ctl = self.integers([self.pending, 0] + [0] * 15)
            request = torch.zeros(self.stride, device="mps", dtype=torch.int32)
            if self.pending:
                draft[: self.pending].copy_(self.saved)
                cfg = self.integers(self.cfg(cap, 0, 0))
                self.lib.refresh_vec(
                    draft,
                    self.roles,
                    self.meta.data,
                    self.identity.data,
                    self.graphs,
                    self.key.data,
                    self.dynamic,
                    self.slot,
                    embeds,
                    cfg,
                    threads=32 * self.pending,
                )
            for last, event, seed in events:
                base = self.cfg(cap, self.rows.get(last, 0), seed)
                config = self.integers([base[:9] + [i] + base[10:] for i in range(4)])
                se = self.upload(torch.cat((m.state, event)))
                ctx = self.upload((m.state + event).tanh())
                self.lib.page_begin(ctl, draft, config[0], threads=1)
                self.leaps(4, config, ctl, se, ctx, buffers, cap)
                self.lib.page_end(
                    ctl,
                    draft,
                    embeds,
                    request,
                    self.roles,
                    schedule,
                    config[0],
                    threads=1,
                )
            report = torch.cat((ctl, request)).cpu()
            self.count["boundary_readbacks"] += 1
            self.count["download_bytes"] += report.numel() * report.element_size()
            self.count["rate_scored_padded_sites"] += len(events) * 4 * (cap + 1)
            self.count["allocated_mark_lanes"] += len(events) * 4 * 2 * cap
            if int(report[2]) == 1:
                # The authoritative tail remains in saved. Replay all unissued edits.
                cap *= 2
                self.count["overflow_restarts"] += 1
                continue
            break
        (
            n,
            _,
            _,
            _,
            draws,
            nodes,
            pivots,
            blocked,
            maxbatch,
            ins,
            sub,
            delete,
            scans,
            reads,
            ready,
            used,
            carried,
        ) = report[:17].tolist()
        self.saved = draft[:n].clone()
        self.pending = n
        self.count["largest_edit_batch"] = max(
            self.count["largest_edit_batch"], maxbatch
        )
        self.count["useful_mark_lanes"] += draws
        self.count["pages"] += used
        self.count["issue_readbacks" if ready else "seal_readbacks"] += 1
        for k, v in {
            "mark_draws": draws,
            "address_forward_calls": nodes,
            "device_pivot_visits": pivots,
            "blocked_dependent_delete": blocked,
            "sampled_edits": ins + sub + delete,
            "edit_forward_calls": 4 * used,
            "device_local_scan_steps": scans,
            "owner_projection_reads": reads,
            "stream_pages": used,
            "carried_unissued": carried,
            "draft_after_edit": carried + ready,
        }.items():
            stats[k] += v
        stats["draft_pending"] = n
        if not ready:
            return used, None
        uid, t, *payload = report[17:].tolist()
        refs = tuple(
            (*self.addresses[payload[i * 3]], payload[i * 3 + 2])
            for i in range(len(m.roles[t // 2]))
        )
        return used, Item(uid, Cell(t // 2, refs, bool(t % 2)))

    def run(self, policy, txn, stats, deadline):
        if policy.arm != "empty" or not policy.waves or policy.steps != 4:
            raise ValueError("expected fixed scheduled D4 stream")
        m = self.m
        events = []
        # FIFO/revisit selection depends only on this publication. It is unchanged by
        # a same-Run CCP reply. The neural state is refreshed after each actual issue.
        for _ in range(policy.waves):
            policy.advance_event(stats)
            if not m.ids:
                break
            events.append((m.last, m.event, int(policy.rng.integers(1, 2**31))))
        signed = set()
        while events:
            if perf_counter() >= deadline:
                raise TimeoutError
            t = perf_counter()
            used, item = self.until_boundary(events, stats)
            stats["sampling_seconds"] += perf_counter() - t
            m.last, m.event, _ = events[used - 1]
            events = events[used:]
            if item is not None:
                stats["final_tokens"] += 1
                stats["same_run_repeat_signed"] += int(item.cell in signed)
                signed.add(item.cell)
                replies = policy.issue((item,), txn, stats)
                if item.uid in replies:
                    self.receipt(item, replies[item.uid])
                policy.consume_reply((item,), replies)

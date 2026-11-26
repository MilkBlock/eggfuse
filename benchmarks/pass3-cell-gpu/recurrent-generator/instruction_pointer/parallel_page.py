"""Parallel complete marks on Metal with one readback at the native page boundary."""

from functools import lru_cache
from pathlib import Path

import torch

from discrete_draft import Cell, Item, valid
from draft_dispatch import Dispatch
from parallel_fit import site_features
from resident_page import Page


@lru_cache(maxsize=2)
def library(width):
    files = [
        Path(__file__).with_name(n).read_text()
        for n in ("draft_page.metal", "parallel_jobs.metal")
    ]
    return torch.mps.compile_shader(
        f"#define SET_PAGE 1\n#define MARK_H {width}\n" + "\n".join(files)
    )


class JointPage(Page):
    def __init__(self, m, marks, rates, counts, method, cap):
        super().__init__(m, marks, rates, counts)
        self.lib = library(self.width)
        self.method, self.cap = method, cap
        self.history = torch.zeros(32, device="mps")

    def sample(self, m, source, steps, rng, stats):
        if steps < 1 or (source and not valid(source)):
            raise ValueError(
                "a page requires positive steps and intact local dependencies"
            )
        cap = max(self.cap, len(source))
        buffers = self.scratch(cap)
        draft, vec, jobs, gen, *_ = buffers
        draft.zero_()
        vec.zero_()
        gen.zero_()
        if source:
            incoming, vectors = self.pack_source(m, source)
            draft[: len(source)].copy_(incoming)
            vec[: len(source)].copy_(vectors)
        next_uid = max((item.uid for item in source), default=-1) + 1
        ctl = self.integers([len(source), next_uid] + [0] * 14)
        state = self.upload(m.state)
        event = (self.upload(m.event) + 0.5 * self.history).tanh()
        base = (state + event).tanh()
        cfg = [
            cap,
            self.slots,
            self.pcs,
            self.tables,
            self.tabrows.data.shape[1],
            self.ownerpc.data.shape[1],
            self.len_vocab,
            self.rows.get(m.last, 0),
            int(rng.integers(1, 2**31)),
            0,
            self.width,
            2 * cap,
        ]
        cfgs = self.integers([cfg[:9] + [i] + cfg[10:] for i in range(steps)])
        settings = self.integers([self.method, steps])
        positions = torch.arange(cap, device="mps")
        blank = torch.zeros(cap, 3, device="mps")
        for i in range(steps):
            live = (positions < ctl[0]).float()
            x, pool = site_features(state, event, vec * live[:, None], live, i / steps)
            logits = self.rates(x) if self.method else blank
            self.lib.set_jobs(logits, ctl, jobs, cfgs[i], settings, threads=1)
            self.apply_marks(
                cfgs[i],
                ctl,
                (base + pool).tanh() if self.method else base,
                buffers,
                cap,
            )
        active = (positions < ctl[0]).float()
        self.history = (
            self.history * 0.5
            + (vec * active[:, None]).sum(0) / active.sum().clamp_min(1)
        ).tanh()
        reply = torch.cat((ctl, draft.flatten())).cpu()
        self.count["boundary_readbacks"] += 1
        self.count["download_bytes"] += reply.numel() * 4
        self.count["allocated_mark_lanes"] += cap * 2 * steps
        self.count["action_sites"] += cap * steps if self.method else 0
        stats["template_tree_decisions"] += int(reply[14])
        stats["template_address_reads"] += int(reply[15])
        stats["parent_tree_and_copy_decisions"] += int(reply[5] - reply[14])
        items = self.unpack(reply, steps, cap, stats, 16)
        if not self.method:
            stats["edit_forward_calls"] -= steps
        return tuple(
            Item(i.uid, Cell(i.cell.rule, i.cell.refs, i.cell.higher, 1))
            if i.cell.rule in m.scalars
            else i
            for i in items
        )


class ParallelPolicy(Dispatch):
    def wire_request(self, cell):
        if desc := self.m.scalars.get(cell.rule):
            return 1, desc.rule, desc.atom, desc.wire(cell.refs)
        return super().wire_request(cell)

    def resume_local(self, frame, txn, stats):
        self.scheduled.update(
            (c, 0) for r, _ in frame["rules"] for c in self.m.by_rule[r]
        )
        return super().resume_local(frame, txn, stats)

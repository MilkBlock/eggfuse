"""Run the existing two-hidden-layer D4 plan on MPS, including sampled named addressing."""

from collections import Counter
from functools import lru_cache
from pathlib import Path
from time import perf_counter

import numpy as np
import torch

from actor import row_features
from discrete_draft import Cell, Item, Local


@lru_cache(maxsize=2)
def shader(width):
    return torch.mps.compile_shader(
        f"#define MARK_H {width}\n"
        + Path(__file__).with_name("draft_page.metal").read_text()
    )


class Slab:
    """Geometric growth, retaining physical row and column indices."""

    def __init__(self, rows, cols, dtype, counts):
        self.dtype = dtype
        self.data = torch.zeros((rows, cols), device="mps", dtype=dtype)
        self.counts = counts

    def reserve(self, rows, cols):
        r, c = self.data.shape
        if rows <= r and cols <= c:
            return
        dest = torch.zeros(
            (
                r if rows <= r else 1 << (rows - 1).bit_length(),
                c if cols <= c else 1 << (cols - 1).bit_length(),
            ),
            dtype=self.dtype,
            device="mps",
        )
        dest[:r, :c].copy_(self.data)
        self.counts["growth_copy_bytes"] += self.data.numel() * self.data.element_size()
        self.data = dest


class Page:
    def __init__(self, m, marks, rates, counts):
        self.count = counts
        self.m = m
        self.rates = rates.to("mps").eval()
        net = marks.choice
        self.width = net[0].out_features
        if len(net) != 5 or self.width not in (136, 512):
            raise ValueError("unsupported mark layout")
        self.lib = shader(self.width)
        self.weights = self.upload(torch.cat([p.flatten() for p in net.parameters()]))
        self.gru = self.upload(
            torch.cat([p.flatten() for p in m.enc.actor.next_read.parameters()])
        )
        self.slots = max(1, max(map(len, m.roles)))
        self.pcs = max(1, max((pc + 1 for d in m.output_tables for pc in d), default=1))
        self.tables = len(m.enc.cat.tables)
        n = len(m.roles)
        role = torch.full((n, self.slots), -1, dtype=torch.int32)
        slot = torch.zeros(n, self.slots, 32)
        graphs = torch.empty(n * 2, 32)
        out = torch.full((n, self.pcs), -1, dtype=torch.int32)
        order = torch.zeros(n, self.pcs, dtype=torch.int32)
        proj = torch.full((n, self.tables), -1, dtype=torch.int32)
        local = torch.zeros(n * 2, self.pcs, 32)
        for r, tabs in enumerate(m.roles):
            for i, tab in enumerate(tabs):
                role[r, i] = tab
                slot[r, i] = m.enc.nodes[m.enc.cat.inputs["generated", r][i]]
            for h in (0, 1):
                graph = m.graph((r, bool(h and r in m.menu)))
                graphs[2 * r + h] = graph
                for pc, tab in m.output_tables[r].items():
                    out[r, pc] = tab
                    node = m.enc.cat.outputs.get((("generated", r), pc))
                    local[2 * r + h, pc] = (
                        graph + (m.enc.nodes[node] if node is not None else 0)
                    ).tanh()
            pcs = list(m.output_tables[r])
            order[r] = torch.tensor(pcs + [k for k in range(self.pcs) if k not in pcs])
            if m.grouped:
                for tab, pc in m.projections[r].items():
                    proj[r, tab] = pc
        self.graphs, self.roles, self.slot, self.outputs, self.locals, self.proj = map(
            self.upload, (graphs, role, slot, out, local, proj)
        )
        self.order = self.upload(order)
        self.vocabs = {}
        self.rows = {}
        self.addresses = [None]
        self.owners = {}
        self.tabrows = Slab(self.tables, 1, torch.int32, counts)
        self.ownerpc = Slab(1, self.pcs, torch.int32, counts)
        self.meta = Slab(1, 5, torch.int32, counts)
        self.key = Slab(1, 32, torch.float32, counts)
        self.idvec = Slab(1, 32, torch.float32, counts)
        self.member = Slab(1, (self.tables + 31) // 32, torch.int32, counts)
        self.bits = Counter()
        self.sizes = [0] * self.tables
        self.sizes_gpu = self.upload(torch.zeros(self.tables, dtype=torch.int32))
        self.last_rules = None
        self.vocab = None
        self.len_vocab = 0
        self.stride = 2 + 3 * self.slots
        self.buffers = {}
        m.on_page_publication = self.publication

    def upload(self, t):
        self.count["upload_bytes"] += t.numel() * t.element_size()
        self.count["uploads"] += 1
        return t.contiguous().to("mps", non_blocking=True)

    def integers(self, values):
        return self.upload(torch.as_tensor(values, dtype=torch.int32))

    def address(self, key):
        if key not in self.rows:
            self.rows[key] = len(self.addresses)
            self.addresses.append(key)
        return self.rows[key]

    def publication(self, frame):
        tick = perf_counter()
        m = self.m
        rules = tuple(r for r, _ in frame["rules"])
        if rules != self.last_rules:
            if rules not in self.vocabs:
                self.vocabs[rules] = self.integers([2 * r + int(h) for r, h in m.ids])
            self.vocab = self.vocabs[rules]
            self.len_vocab = len(m.ids)
            self.last_rules = rules
        changes = {(a["token"], a["op"]) for a in frame["retired"]}
        changes.update((a["token"], a["op"]) for a, _ in frame["updates"])
        if not changes:
            return
        ids = []
        meta = []
        keys = []
        ident = []
        positions = []
        membership = {}
        ownerpos = []
        for addr in sorted(changes):
            gid = self.address(addr)
            entry = m.pub.live.get(addr)
            owner = self.owners.setdefault(addr[0], len(self.owners) + 1)
            ids.append(gid)
            ownerpos.append((owner, addr[1], gid))
            rule = m.owner_rule.get(addr[0], -1)
            if entry is None:
                meta.append([-1, -1, owner, rule, -1])
                keys.append(torch.zeros(32))
                ident.append((0, 0, 0))
                continue
            row, vector = entry
            tab = row["table"]
            ver = row["version"]
            meta.append([tab, ver, owner, rule, tab])
            keys.append(vector)
            ident.append(tuple(x % (1 << 64) for x in (*addr, ver)))
            pos = m.index[tab, addr]
            if pos >= self.sizes[tab] or not self.bits[gid, tab // 32] & (
                1 << (tab % 32)
            ):
                positions.append((tab, pos, gid))
                self.sizes[tab] = max(self.sizes[tab], pos + 1)
                self.bits[gid, tab // 32] |= 1 << (tab % 32)
                membership[gid, tab // 32] = self.bits[gid, tab // 32]
        for slab in (self.meta, self.key, self.member, self.idvec):
            slab.reserve(len(self.addresses), slab.data.shape[1])
        self.ownerpc.reserve(len(self.owners) + 1, max(pc for _, pc, _ in ownerpos) + 1)
        self.tabrows.reserve(self.tables, max(self.sizes))
        idx = self.integers(ids)
        self.meta.data[idx] = self.integers(meta)
        self.key.data[idx] = self.upload(torch.stack(keys))
        self.idvec.data[idx] = self.upload(
            m.enc.actor.dynamic(row_features(ident, 32, "cpu"))
        )

        def scatter(slab, coords):
            if coords:
                mat = self.integers(np.array(coords, dtype=np.int64).astype(np.int32))
                slab.data[mat[:, 0], mat[:, 1]] = mat[:, 2]

        scatter(self.ownerpc, ownerpos)
        scatter(self.tabrows, positions)
        scatter(self.member, [(gid, b, v) for (gid, b), v in membership.items()])
        if positions:
            self.sizes_gpu = self.integers(self.sizes)
        self.count["index_row_updates"] += len(ids)
        self.count["index_update_submit_seconds"] += perf_counter() - tick

    def scratch(self, cap):
        if cap not in self.buffers:
            jobs = 2 * cap

            def t(shape, dtype):
                return torch.empty(shape, device="mps", dtype=dtype)

            self.buffers[cap] = (
                t((cap, self.stride), torch.int32),
                t((cap, 32), torch.float32),
                t((jobs, 2), torch.int32),
                t((jobs, self.stride), torch.int32),
                t((jobs, 32), torch.float32),
                t((jobs, 4), torch.int32),
                t((cap + 1, 166), torch.float32),
            )
        return self.buffers[cap]

    def leaps(self, steps, config, ctl, se, ctx, buffers, cap):
        draft, embeds, jobs, generated, encoded, perjob, features = buffers
        for i in range(steps):
            c = config[i]
            self.lib.rate_features(
                embeds, se, ctl, c, features, threads=features.numel()
            )
            logits = self.rates(features)
            self.lib.jobs(logits, ctl, jobs, c, threads=1)
            self.apply_marks(c, ctl, ctx, buffers, cap)

    def apply_marks(self, c, ctl, ctx, buffers, cap):
        draft, embeds, jobs, generated, encoded, perjob, _ = buffers
        self.lib.draw(
            jobs,
            ctl,
            c,
            draft,
            embeds,
            generated,
            self.vocab,
            self.graphs,
            self.roles,
            self.slot,
            self.outputs,
            self.locals,
            self.tabrows.data,
            self.sizes_gpu,
            self.meta.data,
            self.key.data,
            self.ownerpc.data,
            self.proj,
            self.weights,
            self.gru,
            ctx,
            perjob,
            self.member.data,
            self.order,
            threads=2 * cap * 32,
            group_size=32,
        )
        self.lib.edit_vectors(
            generated,
            ctl,
            c,
            jobs,
            self.roles,
            self.slot,
            self.graphs,
            self.idvec.data,
            self.key.data,
            encoded,
            threads=2 * cap * 32,
        )
        self.lib.apply_jobs(
            draft,
            embeds,
            ctl,
            c,
            jobs,
            generated,
            encoded,
            self.roles,
            self.outputs,
            perjob,
            threads=1,
        )

    def pack_source(self, m, source):
        incoming = torch.zeros((len(source), self.stride), dtype=torch.int32)
        for i, item in enumerate(source):
            cell = item.cell
            incoming[i, 0] = item.uid
            incoming[i, 1] = 2 * cell.rule + int(cell.higher)
            for j, ref in enumerate(cell.refs):
                if isinstance(ref, Local):
                    v = (-1 - ref.owner, ref.port, 0)
                else:
                    v = (self.address(ref[:2]), 0, ref[2])
                incoming[i, 2 + 3 * j : 5 + 3 * j] = torch.tensor(v)
        # A failed local producer may leave an unresolved physical address in a carried
        # draft. It has no published vector or table membership and cannot satisfy a read.
        for slab in (self.meta, self.key, self.member, self.idvec):
            slab.reserve(len(self.addresses), slab.data.shape[1])
        src = self.upload(incoming)
        old = (
            self.upload(torch.stack([m.embed(item.cell) for item in source]))
            if source
            else None
        )
        return src, old

    def sample(self, m, source, steps, rng, stats):
        if steps != 4:
            raise ValueError("device page requires the four-step policy")
        src, old = self.pack_source(m, source)
        se = self.upload(torch.cat((m.state, m.event)))
        ctx = self.upload(m.context())
        seed = int(rng.integers(1, 2**31))
        cap = max(4, 1 << (len(source) + 1).bit_length())
        next_uid = max((item.uid for item in source), default=-1) + 1
        while True:
            draft, embeds, _jobs, generated, _encoded, _perjob, _features = (
                self.scratch(cap)
            )
            draft.zero_()
            generated.zero_()
            if source:
                draft[: len(source)].copy_(src)
                embeds[: len(source)].copy_(old)
            ctl = self.integers([len(source), next_uid] + [0] * 12)
            cfg = [
                cap,
                self.slots,
                self.pcs,
                self.tables,
                self.tabrows.data.shape[1],
                self.ownerpc.data.shape[1],
                self.len_vocab,
                self.rows.get(m.last, 0),
                seed,
                0,
                self.width,
                2 * cap,
            ]
            config = self.integers([cfg[:9] + [i] + cfg[10:] for i in range(steps)])
            self.leaps(steps, config, ctl, se, ctx, self.scratch(cap), cap)
            # A single contiguous read at the issue boundary includes counters and all
            # survivor tokens. Overflow retries with the SAME seed and original draft.
            reply = torch.cat((ctl, draft.flatten())).cpu()
            self.count["boundary_readbacks"] += 1
            self.count["download_bytes"] += reply.numel() * reply.element_size()
            self.count["rate_scored_padded_sites"] += steps * (cap + 1)
            self.count["allocated_mark_lanes"] += steps * cap * 2
            if int(reply[2]):
                self.count["overflow_restarts"] += 1
                cap *= 2
                continue
            break
        return self.unpack(reply, steps, cap, stats)

    def unpack(self, reply, steps, cap, stats, header=14):
        m = self.m
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
            localscans,
            reads,
        ) = reply[:14].tolist()
        for k, v in {
            "mark_draws": draws,
            "address_forward_calls": nodes,
            "device_pivot_visits": pivots,
            "blocked_dependent_delete": blocked,
            "sampled_edits": ins + sub + delete,
            "edit_forward_calls": steps,
            "device_local_scan_steps": localscans,
            "owner_projection_reads": reads,
        }.items():
            stats[k] += v
        self.count["largest_edit_batch"] = max(
            self.count["largest_edit_batch"], maxbatch
        )
        self.count["useful_mark_lanes"] += draws
        self.count["pages"] += 1
        ret = []
        for row in reply[header:].reshape(-1, self.stride)[:n].tolist():
            uid, t = row[:2]
            rid = t // 2
            refs = []
            for j in range(len(m.roles[rid])):
                gid, pc, v = row[2 + 3 * j : 5 + 3 * j]
                refs.append(
                    Local(-1 - gid, pc) if gid < 0 else (*self.addresses[gid], v)
                )
            ret.append(Item(uid, Cell(rid, tuple(refs), bool(t % 2))))
        return tuple(ret)

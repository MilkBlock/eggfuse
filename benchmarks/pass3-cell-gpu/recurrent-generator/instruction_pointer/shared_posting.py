"""Single-field neural postings. Index construction has no Recipe argument."""

from collections import Counter, defaultdict
from dataclasses import dataclass

import numpy as np
import torch

from address_scores import mlp
from binding_model import bit_lanes
from discrete_draft import Cell
from foundation_completion import Completion


HEADS = 4
BINS = 64
STRIDE = BINS + 2
UNITS = 1 << 16
PROPOSALS = 8


@dataclass
class Bank:
    refs: list
    keys: torch.Tensor
    offsets: torch.Tensor
    lo: torch.Tensor
    frac: torch.Tensor
    starts: torch.Tensor
    ends: torch.Tensor
    owners: torch.Tensor
    widths: list
    min_width: int
    max_width: int


class FieldPostings:
    def __init__(self, mapping, device):
        self.mapping = mapping.to(device)
        self.device = device
        self.banks = {}
        self.loc = {}
        self.live_count = Counter()

    def encode(self, values):
        bits = torch.from_numpy(bit_lanes(values)).to(self.device).reshape(1, -1, 1, 64)
        codes, weights = self.mapping(bits, "mixed-sparse", fixed_order=True)
        scaled = (codes[0, :, :, 0].float() + weights[0, :, :, 1]).T * (
            BINS / self.mapping.resolution
        )
        return scaled.floor().int(), scaled.frac()

    def publish(self, m, frame, stats):
        edits = defaultdict(dict)
        for a in frame["retired"]:
            key = a["token"], a["op"]
            if key in self.loc:
                edits[self.loc[key][0]][key] = None
        updates = frame["updates"]
        if updates:
            values = [v for _, r in updates for v in r["hashes"]]
            if values:
                lo, frac = self.encode(values)
            else:
                lo = torch.empty((0, HEADS), device=self.device, dtype=torch.int32)
                frac = lo.float()
            keys = torch.stack([m.key((a["token"], a["op"])) for a, _ in updates]).to(
                self.device
            )
            start = 0
            for i, (a, r) in enumerate(updates):
                key = a["token"], a["op"]
                table = r["table"]
                if key in self.loc and self.loc[key][0] != table:
                    old = self.loc[key][0]
                    if key not in edits[old] or edits[old][key] is not None:
                        raise ValueError("type change without retirement")
                stop = start + len(r["hashes"])
                edits[table][key] = (
                    (*key, r["version"]),
                    keys[i],
                    lo[start:stop],
                    frac[start:stop],
                )
                start = stop
            stats["fields_encoded"] += len(values)
            stats["rows_encoded"] += len(updates)
        # Only touched tables are repacked. Surviving rows reuse their actual
        # publication encoding. Row relocation never changes a named reference.
        for table, changed in edits.items():
            rows = {}
            old = self.banks.pop(table, None)
            if old is not None:
                pos = 0
                for i, (ref, w) in enumerate(zip(old.refs, old.widths, strict=True)):
                    k = ref[:2]
                    if self.loc.get(k, (None,))[0] == table:
                        self.loc.pop(k, None)
                    if k not in changed:
                        rows[k] = (
                            ref,
                            old.keys[i],
                            old.lo[pos : pos + w],
                            old.frac[pos : pos + w],
                        )
                    pos += w
            rows.update((k, v) for k, v in changed.items() if v is not None)
            self.live_count[table] = len(rows)
            if not rows:
                continue
            refs, keys, lowers, weights = zip(*rows.values())
            widths = [len(x) for x in lowers]
            lo, frac = torch.cat(lowers), torch.cat(weights)
            dev = self.device
            offsets = np.cumsum([0, *widths])
            owners = np.repeat(np.arange(len(rows), dtype=np.int32), widths)
            cols = torch.as_tensor(np.arange(len(owners)) - offsets[owners], device=dev)
            h = torch.arange(HEADS, device=dev)
            labels = (cols[:, None] * HEADS + h) * STRIDE + lo
            labels = torch.stack((labels, labels + 1), -1).flatten()
            labels, order = labels.sort()
            limit = max(widths) * HEADS * STRIDE
            starts = torch.searchsorted(
                labels, torch.arange(limit + 1, device=dev)
            ).int()
            units = (frac * UNITS).round().int()
            mass = torch.stack((UNITS - units, units), -1).flatten()[order]
            ends = torch.nn.functional.pad(mass.long().cumsum(0), (1, 0))
            row = torch.as_tensor(owners, device=dev)[order // (HEADS * 2)]
            self.banks[table] = Bank(
                list(refs),
                torch.stack(keys),
                torch.as_tensor(offsets, device=dev),
                lo,
                frac,
                starts,
                ends,
                row,
                widths,
                min(widths),
                max(widths),
            )
            self.loc.update((ref[:2], (table, i)) for i, ref in enumerate(refs))
            stats["maintenance_rows_copied"] += len(rows)
            stats["postings_rebuilt"] += len(row)

    def bytes(self):
        return sum(
            t.nbytes
            for b in self.banks.values()
            for t in vars(b).values()
            if torch.is_tensor(t)
        )


def field(bank, row, col):
    # Ragged physical banks may include a row without a projected field.
    # Missing positions have zero neural mass and remain in uniform exploration.
    ix = bank.offsets[row] + col
    if col < bank.min_width:
        return ix, None
    return ix.clamp_max(len(bank.lo) - 1), ix < bank.offsets[row + 1]


def propose(bank, wires, u):
    """Draw with replacement from a mixture of lossy neural buckets and uniform rows.
    A wire holds (source-bank, batched source-row, source-col, target-col).
    All independent domain rows retain positive probability."""
    n = len(bank.refs)
    uniform = (u[..., 0] * n).long().clamp_max(n - 1)
    if not wires:
        return uniform
    labels, weights = [], []
    heads = torch.arange(HEADS, device=u.device)
    for src, row, a, b in wires:
        if a >= src.max_width or b >= bank.max_width:
            continue
        ix, present = field(src, row, a)
        f = src.frac[ix]
        lower = (b * HEADS + heads) * STRIDE + src.lo[ix]
        labels.append(torch.stack((lower, lower + 1), -1).flatten(1))
        w = torch.stack((1 - f, f), -1).flatten(1)
        weights.append(w if present is None else w * present[:, None])
    if not labels:
        return uniform
    ch = torch.cat(labels, 1).long()
    start = bank.ends[bank.starts[ch].long()]
    size = bank.ends[bank.starts[ch + 1].long()] - start
    mass = torch.cat(weights, 1) * size.float()
    acc = mass.cumsum(1)
    ix = torch.searchsorted(
        acc.contiguous(), (u[..., 1] * acc[:, -1:]).contiguous(), right=True
    ).clamp_max(ch.size(1) - 1)
    count = size.gather(1, ix)
    offset = torch.minimum((u[..., 2] * count.float()).long(), (count - 1).clamp_min(0))
    pos = (
        torch.searchsorted(
            bank.ends, (start.gather(1, ix) + offset).contiguous(), right=True
        )
        - 1
    )
    hit = bank.owners[pos.clamp(0, len(bank.owners) - 1)].long()
    return torch.where((acc[:, -1:] <= 0) | (u[..., 3] < 0.05), uniform, hit)


def same_row_score(bank, ids, wires):
    s = bank.keys.new_zeros(ids.shape)
    for src, row, a, b in wires:
        if a >= src.max_width or b >= bank.max_width:
            continue  # Uniform across this set of proposals.
        ix, x_present = field(src, row, a)
        iy, y_present = field(bank, ids, b)
        delta = bank.lo[iy] - src.lo[ix][:, None]
        x, y = src.frac[ix][:, None], bank.frac[iy]
        # Dot product of two 2-sparse interpolation vectors per learned head.
        dot = (
            (delta == 0) * ((1 - x) * (1 - y) + x * y)
            + (delta == 1) * x * (1 - y)
            + (delta == -1) * (1 - x) * y
        )
        if y_present is not None:
            dot = dot * y_present[..., None]
        if x_present is not None:
            dot = dot * x_present[:, None, None]
        s += dot.mean(-1).clamp_min(0.005).log()
    return s


class SparseCompletion(Completion):
    def __init__(self, model, device="mps", anchor=False):
        super().__init__(model, "rule", device)
        self.mem = FieldPostings(model.mapping, device)
        self.anchor = anchor

    def bind(self, rid, slots, rng, stats):
        tabs, roles = self.schemas[rid]
        if any(not self.mem.live_count[t] for t in tabs):
            stats["empty_domain"] += slots
            return [None] * slots
        return self.complete(rid, slots, rng, stats, [])

    def complete(self, rid, slots, rng, stats, bound):
        tabs, roles = self.schemas[rid]
        previous = [bank.keys[row] for bank, row in bound]
        for j in range(len(bound), len(tabs)):
            t = tabs[j]
            bank = self.mem.banks[t]
            q = self.ctx + self.rkeys[self.rpos[rid]] + roles[j]
            if previous:
                q = q + torch.stack(previous).mean(0)
            q = q.tanh().expand(slots, -1)
            wires = [
                (src, row, a, b)
                for i, (src, row) in enumerate(bound)
                for a, b in self.wiring[rid][i, j]
            ]
            u = torch.from_numpy(
                rng.random((slots, PROPOSALS, 5), dtype=np.float32)
            ).to(self.device)
            guide = None
            if self.anchor and j == 0:
                nxt = next(
                    (i for i in range(1, len(tabs)) if self.wiring[rid][i, j]), None
                )
                if nxt is not None:
                    # Random probes see physical rows, including irrelevant ones.
                    # Neither a host-supplied correct anchor nor an asserted parent.
                    source = self.mem.banks[tabs[nxt]]
                    probes = torch.from_numpy(
                        rng.integers(len(source.refs), size=slots * PROPOSALS)
                    ).to(self.device)
                    guide = [
                        (source, probes, a, b) for a, b in self.wiring[rid][nxt, j]
                    ]
            if guide:
                guided = propose(bank, guide, u.reshape(-1, 1, 5))
                ids = guided.reshape(slots, PROPOSALS)
                support = same_row_score(bank, guided, guide).reshape_as(ids)
                stats["anchor_probes"] += slots * PROPOSALS
                stats["channel_probes"] += slots * PROPOSALS * len(guide) * HEADS * 2
                stats["same_row_field_scores"] += slots * PROPOSALS * len(guide)
            else:
                ids = propose(bank, wires, u)
                support = 0
            k = bank.keys[ids].reshape(-1, 32)
            query = q[:, None].expand(-1, PROPOSALS, -1).reshape_as(k)
            zero = torch.zeros_like(k)
            prior = (
                mlp(self.net.scorer, query, zero, k, 1)
                - mlp(self.net.scorer, query, k, zero, 1)
            ) / 2
            logits = prior.view_as(ids) + same_row_score(bank, ids, wires) + support
            ix = torch.searchsorted(
                logits.softmax(1).cumsum(1).contiguous(), u[:, :1, 4].contiguous()
            ).clamp_max(PROPOSALS - 1)
            row = ids.gather(1, ix).squeeze(1)
            previous.append(bank.keys[row])
            bound.append((bank, row))
            stats["proposal_rows"] += slots * PROPOSALS
            stats["channel_probes"] += slots * len(wires) * HEADS * 2
            stats["same_row_field_scores"] += slots * PROPOSALS * len(wires)
        if not bound:
            return [Cell(rid, ()) for _ in range(slots)]
        rows = torch.stack([row for _, row in bound], 1).cpu().tolist()
        return [
            Cell(
                rid, tuple(bank.refs[i] for (bank, _), i in zip(bound, rr, strict=True))
            )
            for rr in rows
        ]

"""Publication-owned physical pages. The index has no Recipe input."""

from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import torch

from binding_model import bit_lanes


@dataclass
class Page:
    table: int
    refs: list
    keys: torch.Tensor
    fields: torch.Tensor
    mean: torch.Tensor


class AssociationMemory:
    def __init__(self, projection, device, width=32):
        self.device = device
        self.width = width
        # Reuse the previous field map's coordinate selection and learned bit weights.
        # The single-field dot equals a weighted identity-bit similarity.
        self.coords = projection.coords.to(device)
        self.weights = (
            projection.logits.detach().to(device).softmax(-1) / self.coords.size(0)
        ).sqrt()
        self.rows = {}
        self.segments = []
        self.pages = {}
        self.by_table = defaultdict(list)
        self.live_count = defaultdict(int)
        self.front = {}

    def publish(self, m, frame, stats):
        touched = set()
        for a in frame["retired"]:
            key = (a["token"], a["op"])
            if key in self.rows:
                pg, *_ = self.rows.pop(key)
                self.segments[pg].pop(key)
                self.live_count[self.pages[pg].table] -= 1
                touched.add(pg)
        updates = frame["updates"]
        # Encode only changed fields; groups permit variable or empty field lists.
        by_width = defaultdict(list)
        for a, rec in updates:
            by_width[len(rec["hashes"])].append(((a["token"], a["op"]), rec))
        for width, items in by_width.items():
            values = np.asarray([r["hashes"] for _, r in items], dtype=np.uint64)
            bits = torch.from_numpy(bit_lanes(values)).to(self.device)
            fields = (bits[..., self.coords] * self.weights).flatten(-2)
            keys = torch.stack([m.key(key) for key, _ in items]).to(self.device)
            for i, (key, r) in enumerate(items):
                t = r["table"]
                if key in self.rows:
                    pg = self.rows[key][0]
                    if pg not in self.by_table[t]:
                        raise ValueError("port changed type without retirement")
                else:
                    pg = self.front.get(t)
                    if pg is None or len(self.segments[pg]) >= self.width:
                        pg = len(self.segments)
                        self.segments.append({})
                        self.by_table[t].append(pg)
                        self.front[t] = pg
                    self.live_count[t] += 1
                ref = (*key, r["version"])
                self.rows[key] = (pg, ref, keys[i].clone(), fields[i].clone())
                self.segments[pg][key] = None
                touched.add(pg)
            stats["fields_encoded"] += width * len(items)
        for pg in touched:
            values = [self.rows[key] for key in self.segments[pg]]
            if not values:
                self.pages.pop(pg, None)
                continue
            _, refs, keys, fields = zip(*values)
            keys = torch.stack(keys)
            t = m.pub.live[refs[0][:2]][0]["table"]
            self.pages[pg] = Page(
                t, list(refs), keys, torch.stack(fields), keys.mean(0)
            )
            stats["maintenance_rows_copied"] += len(refs)
        stats["rows_encoded"] += len(updates)

    def groups(self, table=None):
        if table is None:
            return sorted(self.pages)
        return [pg for pg in self.by_table.get(table, ()) if pg in self.pages]

    def lookup(self, ref):
        pg, live, key, fields = self.rows[ref[:2]]
        if ref != live:
            raise ValueError("stale named reference")
        return pg, key, fields

    def bytes(self):
        # Payload resident in individually owned row tensors plus packed page tensors.
        def size(x):
            return x.numel() * x.element_size()

        return sum(size(k) + size(f) for _, _, k, f in self.rows.values()) + sum(
            size(p.keys) + size(p.fields) + size(p.mean) for p in self.pages.values()
        )

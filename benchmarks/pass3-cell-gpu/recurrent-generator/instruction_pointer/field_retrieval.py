"""Persistent role-addressed field embeddings and hash-bucket lookups for frozen Cell memory."""

from collections import defaultdict

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from composition_relation import bits


class FieldEncoder(nn.Module):
    def __init__(self, width=24):
        super().__init__()
        self.shared = nn.Linear(64, width, bias=False)
        self.query = nn.Linear(width, width, bias=False)
        nn.init.eye_(self.query.weight)

    def forward(self, x, query=False):
        h = self.shared(x)
        return F.normalize(self.query(h) if query else h, dim=-1)


class FieldIndex:
    def __init__(self, encoder):
        self.encoder = encoder
        self.keys = {}
        self.queries = {}
        self.rows = {}
        self.owners = defaultdict(dict)
        self.buckets = defaultdict(set)
        self.planes = torch.randn(
            encoder.query.out_features, 8, generator=torch.Generator().manual_seed(711)
        )
        self.writes = self.removes = 0

    def code(self, vectors):
        return ((vectors @ self.planes >= 0).long() * (2 ** torch.arange(8))).sum(-1)

    def advance(self, frame):
        self.advance_rows(
            ((a["token"], a["op"]) for a in frame["retired"]),
            (
                ((a["token"], a["op"]), row["table"], tuple(row["hashes"]))
                for a, row in frame["updates"]
            ),
        )

    def advance_rows(self, retired, updates):
        def detach(address, column, table, code):
            bucket = (table, column, code)
            self.buckets[bucket].remove(address)
            if not self.buckets[bucket]:
                del self.buckets[bucket]
            self.removes += 1

        for address in retired:
            table, hashes, codes = self.rows.pop(address)
            for col, code in enumerate(codes):
                detach(address, col, table, code)
            del (
                self.keys[address],
                self.queries[address],
                self.owners[address[0]][address],
            )
            if not self.owners[address[0]]:
                del self.owners[address[0]]

        changed = []
        for address, table, hashes in updates:
            previous = self.rows.get(address)
            if previous is None:
                n = len(hashes)
                width = self.encoder.query.out_features
                self.keys[address] = torch.empty(n, width)
                self.queries[address] = torch.empty(n, width)
                self.owners[address[0]][address] = self.keys[address]
                codes = [None] * n
            else:
                old_table, old_hashes, codes = previous
                if table != old_table or len(hashes) != len(old_hashes):
                    raise ValueError("typed port changed its static interface")
            for col, value in enumerate(hashes):
                if previous is not None:
                    if value == old_hashes[col]:
                        continue
                    detach(address, col, table, codes[col])
                changed.append((address, table, col, value))
            self.rows[address] = table, hashes, codes
        if not changed:
            return
        raw = torch.from_numpy(np.stack([bits(value) for _, _, _, value in changed]))
        keys = self.encoder(raw)
        queries = self.encoder(raw, True)
        for (address, table, col, _), key, query, code in zip(
            changed, keys, queries, self.code(keys).tolist(), strict=True
        ):
            self.keys[address][col] = key
            self.queries[address][col] = query
            self.rows[address][2][col] = code
            self.buckets[table, col, code].add(address)
            self.writes += 1

    def shortlist(self, probes):
        found = set()
        for query, tab, col in probes:
            code = self.code(query).item()
            for near in [code, *[code ^ (1 << j) for j in range(8)]]:
                found.update(
                    address[0] for address in self.buckets.get((tab, col, near), ())
                )
        return found

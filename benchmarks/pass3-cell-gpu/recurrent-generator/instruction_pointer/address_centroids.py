"""Query-independent, lossless physical layout of learned keys. Reindex affected typed domains on Metal."""

from collections import defaultdict
from time import perf_counter

import torch

from address_scores import cluster, tree


class Centroids:
    def __init__(self, page):
        self.page = page
        self.members = defaultdict(set)
        self.layout = {}
        self.used = 0
        self.offset = torch.zeros(page.tables + 1, dtype=torch.int32, device="mps")
        self.order = torch.empty(1, dtype=torch.int32, device="mps")
        self.nodes = torch.empty((1, 64), device="mps")

    def replace(self, tab, keys):
        n = len(keys)
        if not n:
            return
        pos, room = self.layout.get(tab, (0, 0))
        if room < n:
            pos = self.used
            room = 1 << (n - 1).bit_length()
            self.used += room
            self.layout[tab] = (pos, room)
            if self.used > len(self.order):
                size = 1 << (self.used - 1).bit_length()
                order = self.order.new_empty(size)
                nodes = self.nodes.new_empty((size, 64))
                order[: len(self.order)].copy_(self.order)
                nodes[: len(self.nodes)].copy_(self.nodes)
                self.page.count["semantic_growth_copy_bytes"] += len(self.order) * 260
                self.order, self.nodes = order, nodes
            self.offset[tab] = pos
        if n == 1:
            self.order[pos] = 0
        else:
            order, l, r = cluster(keys)
            self.order[pos : pos + n].copy_(order.int())
            mid = torch.from_numpy(tree(n)[-1][:, 1].copy()).to("mps")
            self.nodes[mid + pos] = torch.cat((l, r), 1)
        self.page.count["semantic_keys_reindexed"] += n
        self.page.count["semantic_rebuilds"] += 1

    def update(self, frame, changed_vocab):
        start = perf_counter()
        page = self.page
        changed = set()
        for addr, row in frame["updates"]:
            member = self.members[addr["token"], addr["op"]]
            member.add(row["table"])
            changed.update(member)
        for addr in frame["retired"]:
            changed.update(self.members[addr["token"], addr["op"]])
        if changed_vocab:
            self.replace(page.tables, page.graphs[page.vocab.long()])
        for tab in sorted(changed):
            ids = page.tabrows.data[tab, : page.sizes[tab]].long()
            self.replace(tab, page.key.data[ids])
        page.address_index = (self.offset, self.order, self.nodes)
        page.count["semantic_cached_bytes"] = (
            self.nodes.numel() * 4 + self.order.numel() * 4 + self.offset.numel() * 4
        )
        page.count["semantic_update_submit_seconds"] += perf_counter() - start

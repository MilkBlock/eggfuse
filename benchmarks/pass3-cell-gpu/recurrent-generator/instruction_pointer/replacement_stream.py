"""Exclude only versioned named tuples acknowledged in this frozen Run."""

from bisect import bisect_left
from collections import defaultdict
import numpy as np
import torch
from stream_guard import GuardStream


def intervals(total, holes, block):
    start = 0
    for end in sorted(set(holes)) + [total]:
        for i in range(start, end, block):
            yield torch.arange(i, min(end, i + block))
        start = end + 1


class ReplacementStream(GuardStream):
    def covered_paths(self, completed):
        out = set()
        for parents in completed:
            path = []
            for depth, role in enumerate(self.order):
                t, pc, ver = parents[role]
                ports = self.roles[depth]
                a = (t, pc)
                i = bisect_left(ports, a)
                if (
                    i == len(ports)
                    or ports[i] != a
                    or self.rd.store.visible[a]["version"] != ver
                ):
                    break
                path.append(i)
            else:
                out.add(tuple(path))
        return out

    def remove_scored(self, paths, covered, counts):
        """Remove acknowledged requests that survived ordinary proposal scoring."""
        keep = torch.ones(len(paths), dtype=torch.bool)
        for row in covered:
            keep &= ~(paths == paths.new_tensor(row)).all(1)
        counts["suppressed_after_score"] += int((~keep).sum())
        return paths[keep]

    def locate(self, paths):
        wanted = defaultdict(list)
        for row in self.exclusions:
            wanted[row[:-1]].append(row[-1])
        for i, p in enumerate(paths.tolist()):
            for col in wanted.get(tuple(p), ()):
                yield i, col

    def children(self, paths, depth, block):
        if not self.exclusions or depth + 1 != len(self.roles) or self.links[depth]:
            yield from super().children(paths, depth, block)
            return
        size = len(self.roles[depth])
        holes = [i * size + j for i, j in self.locate(paths)]
        self.stats["omitted_positions"] += len(holes)
        for ix in intervals(len(paths) * size, holes, block):
            yield ix // size, ix % size

    def posting_batches(self, paths, depth, order, base, starts, ends, total, block):
        if not self.exclusions or depth + 1 != len(self.roles):
            yield from super().posting_batches(
                paths, depth, order, base, starts, ends, total, block
            )
            return
        holes = []
        bank = order.numpy()
        for i, col in self.locate(paths):
            segment = bank[int(base[i]) : int(base[i] + ends[i] - starts[i])]
            loc = np.searchsorted(segment, col)
            if loc < len(segment) and segment[loc] == col:
                holes.append(int(starts[i]) + loc)
        self.stats["omitted_positions"] += len(holes)
        self.stats["receipt_posting_lookups"] += len(self.exclusions)
        for ix in intervals(total, holes, block):
            parent = torch.searchsorted(ends, ix, right=True)
            yield parent, order[base[parent] + ix - starts[parent]]

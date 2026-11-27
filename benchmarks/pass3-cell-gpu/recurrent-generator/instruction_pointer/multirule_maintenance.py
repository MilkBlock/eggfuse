"""Publication-segment maintenance audit of joint leaf postings against fresh builds."""

import json
from collections import Counter
from time import perf_counter

import numpy as np
import torch

from binding_model import bit_lanes, tensor
from first_parent import records
from head_joint_index import PostingIndex
from partner_index_worlds import args, frozen


class Segments:
    """Rebuild touched physical buckets before the next read in this single-threaded harness."""

    def __init__(self, model, width=32):
        self.model = model
        self.width = width
        self.slot = {}
        self.buckets = {}
        self.segments = {}
        self.next_slot = 0

    def encode(self, records):
        bits = tensor(bit_lanes(np.asarray([r[1] for r in records], np.uint64)[None]))
        return self.model.mapping(bits, self.model.variant, fixed_order=True)

    def build(self, rows):
        refs = list(rows)
        feats = self.encode([rows[r] for r in refs])
        index = PostingIndex.build(feats, feats[1].new_ones((1, len(refs))))
        return [(r, rows[r][0]) for r in refs], feats, index

    def publish(self, retired, updates):
        changed = set()
        for key in retired:
            part = self.slot.pop(key, None)
            if part is not None:
                self.buckets[part].pop(key)
                changed.add(part)
        for key, record in updates:
            if key not in self.slot:
                self.slot[key] = self.next_slot // self.width
                self.next_slot += 1
            part = self.slot[key]
            self.buckets.setdefault(part, {})[key] = record
            changed.add(part)
        for part in changed:
            rows = self.buckets[part]
            if rows:
                self.segments[part] = self.build(rows)
            else:
                self.segments.pop(part, None)
        return sum(len(self.buckets[p]) for p in changed)


def units(index, refs):
    # Decode immutable posting keys into their original two full-width half codes.
    k = index.keys[0]
    divisor = index.dictionaries[1].size(1) + 1
    hi = index.dictionaries[0][0, k // divisor].cpu().tolist()
    lo = index.dictionaries[1][0, k % divisor].cpu().tolist()
    owner = index.owners[0].cpu().tolist()
    u = index.ends.diff()[0].cpu().tolist()
    return {
        (refs[b], x, y): w for x, y, b, w in zip(hi, lo, owner, u, strict=True) if w
    }


@torch.no_grad()
def run(a):
    model = frozen(a, a.seeds[0])
    rows = []
    for case, tab in (("fact", 205), ("sum-divisors", 223), ("dynamic-0", 47)):
        bank = Segments(model)
        counts = Counter()
        truth = {}
        elapsed = 0
        for line in (a.out / "corpus" / case / "frames").open():
            f = json.loads(line)

            def key(addr):
                return addr["token"], addr["op"]

            ret = [key(addr) for addr in f["retired"] if key(addr) in truth]
            up = [
                (key(addr), (port["version"], port["hashes"]))
                for addr, port in f["updates"]
                if port["table"] == tab
            ]
            if not ret and not up:
                continue
            for k in ret:
                truth.pop(k)
            for k, v in up:
                if k in truth and v[0] != truth[k][0]:
                    counts["new_versions"] += 1
                    before = bank.encode([truth[k]])[0]
                    after = bank.encode([v])[0]
                    counts["cross_bin"] += int((before != after).any())
                truth[k] = v
            torch.mps.synchronize()
            t = perf_counter()
            written = bank.publish(ret, up)
            torch.mps.synchronize()
            elapsed += perf_counter() - t
            counts.update(
                publications=1,
                retired=len(ret),
                upserts=len(up),
                segment_rows=written,
                fresh_rows=len(truth),
            )
            if truth:
                refs, features, idx = bank.build(truth)
                oracle = units(idx, refs)
                actual = {}
                for refs2, _, idx2 in bank.segments.values():
                    actual.update(units(idx2, refs2))
                assert oracle == actual
                # Queries whose features changed must also receive the same aggregate.
                q = tuple(x[:, :, :3] for x in features)
                expected = idx.lookup(q)[2]
                got = sum(ix.lookup(q)[2] for _, _, ix in bank.segments.values())
                torch.testing.assert_close(got, expected, atol=1e-5, rtol=1e-5)
            else:
                assert not bank.segments
        rows.append(dict(case=case, table=tab, **counts, maintenance_s=elapsed))
        records(a.out / "maintenance.csv", rows)
        print(rows[-1], flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args())

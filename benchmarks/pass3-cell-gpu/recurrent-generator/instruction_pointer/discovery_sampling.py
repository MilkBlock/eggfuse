"""Offline controls on complete physical Tokens; no semantic fields enter random sampling."""

import bisect
import json
import math
import random
from collections import Counter, defaultdict
from types import SimpleNamespace

import numpy as np
import torch

from discovery_states import cli, save
from discrete_draft import Cell
from query_environment import conditioned, setup
from recursive_train import folder, read
from response_study import memory


class Domain:
    """Mixed-radix rank for (template, typed published addresses), with arbitrary-size counts."""

    def __init__(self, m):
        self.tables = defaultdict(list)
        for (owner, op), (row, _) in m.pub.live.items():
            self.tables[row["table"]].append((owner, op, row["version"]))
        self.entries = []
        self.ends = []
        self.size = 0
        for rule, higher in m.ids:
            tabs = [self.tables[t] for t in m.roles[rule]]
            count = math.prod(map(len, tabs))
            if count:
                self.size += count
                self.entries.append((rule, higher, tabs, count))
                self.ends.append(self.size)

    def decode(self, index):
        if not 0 <= index < self.size:
            raise IndexError(index)
        t = bisect.bisect_right(self.ends, index)
        rule, higher, tabs, _ = self.entries[t]
        v = index - (self.ends[t - 1] if t else 0)
        refs = []
        for bank in tabs:
            v, j = divmod(v, len(bank))
            refs.append(bank[j])
        return Cell(rule, tuple(refs), higher)

    def draw(self, mode, rng, limit):
        if mode not in {"uniform", "unique", "factored"}:
            raise ValueError(mode)
        if not self.size:
            return
        swaps = {}
        for i in range(limit):
            if mode == "unique":
                if i == self.size:
                    return
                j = rng.randrange(i, self.size)
                index = swaps.pop(j, j)
                if j != i:
                    swaps[j] = swaps.pop(i, i)
            elif mode == "factored":
                t = rng.randrange(len(self.entries))
                index = self.ends[t] - 1 - rng.randrange(self.entries[t][3])
            else:
                index = rng.randrange(self.size)
            yield self.decode(index)


def encode(c):
    return [c.rule, c.higher, c.refs]


def seed_for(r, seed):
    return 76139 + 991 * r + 104729 * seed


@torch.no_grad()
def generate(a, case, source):
    dest = a.out / source / case
    selected = {v["run"] for v in read(dest / "states.json")}
    args = SimpleNamespace(**(vars(a) | {"out": a.contract}))
    d = folder(a.data, case)
    ms = {"A": memory(a, d), "D": conditioned(a, d, dest / "scheduler.jsonl")}
    pages = {k: setup(args, m, k, 256)[2] for k, m in ms.items()}
    contexts = (
        read(a.out / "dirty" / case / "contexts.json") if source == "rollout" else {}
    )
    try:
        for line in (dest / "frames.jsonl").open():
            frame = json.loads(line)
            r = frame["run"]
            if r > max(selected):
                break
            for m in ms.values():
                m.update(frame)
            if r not in selected:
                continue
            path = dest / str(r) / "samples.json"
            if path.exists():
                saved = read(path)
                if saved["goal"] != min(a.budget, saved["size"]) or len(saved["records"]) != a.seeds:
                    raise ValueError(f"saved budget or seed count differs at {path}")
                continue
            if source == "rollout" and str(r) in contexts:
                last, event, state, ctx = contexts[str(r)]
                for m in ms.values():
                    m.last = tuple(last) if last else None
                    m.event = torch.tensor(event)
                ms["D"].state = torch.tensor(state)
                torch.testing.assert_close(
                    ms["D"].context(), torch.tensor(ctx), rtol=0, atol=0
                )
            domain = Domain(ms["A"])
            goal = min(a.budget, domain.size)
            records = []
            for seed in range(a.seeds):
                batches = {}
                for arm, m in ms.items():
                    rng = np.random.default_rng(seed_for(r, seed))
                    items = []
                    attempts = 0
                    stats = Counter()
                    while len(items) < goal and attempts < 8192:
                        page = pages[arm]
                        page.cap = min(256, max(16, goal - len(items)))
                        items.extend(i.cell for i in page.sample(m, (), 1, rng, stats))
                        attempts += page.cap
                    batches[arm] = dict(
                        items=list(map(encode, items[:goal])), attempts=attempts
                    )
                n = min([goal] + [len(b["items"]) for b in batches.values()])
                for b in batches.values():
                    b["items"] = b["items"][:n]
                for arm in ("uniform", "unique", "factored"):
                    draws = domain.draw(arm, random.Random(seed_for(r, seed)), n)
                    batches[arm] = dict(items=list(map(encode, draws)), attempts=n)
                records.append(dict(seed=seed, n=n, batches=batches))
            save(path, dict(size=domain.size, goal=goal, records=records))
    finally:
        ms["D"].close_observer()
    print(case, source, flush=True)


if __name__ == "__main__":
    p = cli()
    p.add_argument("--seeds", type=int, default=5)
    p.add_argument("--budget", type=int, default=256)
    a = p.parse_args()
    torch.set_num_threads(1)
    for case in a.cases:
        for source in ("teacher", "rollout"):
            generate(a, case, source)

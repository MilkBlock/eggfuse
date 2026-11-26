"""End-to-end matched complete-Token budgets. Random controls own their domain construction costs."""

import random
from collections import Counter
from itertools import islice
from types import SimpleNamespace

import torch

from address_runtime import native
from discovery_sampling import Domain, seed_for
from discovery_states import cli
from discrete_draft import Item
from query_environment import online_memory, setup


def configure(a, m, arm, cap):
    args = SimpleNamespace(**(vars(a) | {"out": a.contract}))
    if arm in ("A", "D"):
        marks, rates, page = setup(args, m, arm, cap)
        publish = page.publication
        generate = page.sample
    else:
        page = SimpleNamespace(count=Counter())
        marks = SimpleNamespace(resident_page=page)
        rates = None
        publish = lambda frame: None
    by_type = Counter()
    addresses = {}

    def publication(frame):
        publish(frame)
        # Only static type cardinalities determine the common finite-domain cap.
        for addr in frame["retired"]:
            k = (addr["token"], addr["op"])
            by_type[addresses.pop(k)] -= 1
        for addr, row in frame["updates"]:
            k = (addr["token"], addr["op"])
            if k in addresses:
                by_type[addresses[k]] -= 1
            addresses[k] = row["table"]
            by_type[row["table"]] += 1
        from math import prod

        n = sum(prod(by_type[t] for t in m.roles[r]) for r, h in m.ids)
        page.remaining = min(n, cap * a.pages)
        if arm not in ("A", "D"):
            domain = Domain(m)
            assert domain.size == n
            page.count["random_indexed_rows"] += len(addresses)
            page.draws = domain.draw(
                arm,
                random.Random(seed_for(frame["run"], a.generation_seed)),
                page.remaining,
            )

    def sample(mem, source, steps, rng, stats):
        goal = min(cap, page.remaining)
        page.remaining -= goal
        if arm not in ("A", "D"):
            draws = list(islice(page.draws, goal))
        else:
            draws = []
            attempts = 0
            while len(draws) < goal and attempts < 1024:
                page.cap = min(1024 - attempts, max(16, goal - len(draws)))
                draws.extend(x.cell for x in generate(mem, source, steps, rng, stats))
                attempts += page.cap
            page.count["neural_slot_attempts"] += attempts
            page.count["complete_shortfall"] += max(0, goal - len(draws))
        return tuple(Item(i, c) for i, c in enumerate(draws[:goal]))

    m.on_page_publication = publication
    page.sample = sample
    return marks, rates, page


if __name__ == "__main__":
    p = cli()
    p.add_argument("--blocks", type=int, default=2)
    p.add_argument("--cap", type=int, default=16)
    p.add_argument("--pages", type=int, default=2)
    p.add_argument("--seconds", type=int, default=300)
    p.add_argument(
        "--arms", nargs="+", default=["uniform", "unique", "factored", "A", "D"]
    )
    p.add_argument("--generation-seed", type=int, default=536)
    p.add_argument("--paired-clock", action="store_true")
    a = p.parse_args()
    if a.paired_clock:
        a.out = a.out / "paired"
    if a.generation_seed != 536:
        a.out = a.out / "seeds" / str(a.generation_seed)
    torch.set_num_threads(1)
    native(a, configure, online_memory)

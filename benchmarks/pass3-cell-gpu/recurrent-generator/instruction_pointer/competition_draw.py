"""Sample the frozen factorization; remove only issued complete named leaves on this page."""

import numpy as np


class Page:
    def __init__(self, net, w, state):
        self.net = net
        self.w = w
        self.m = net.state(w, state)
        self.roots = tuple(self.m["families"])
        self.base = {}
        self.net_calls = 0

    def transition(self, key):
        stage, rid, tid, prefix = key
        net, m = self.net, self.m
        if stage == "root":
            lp = m["root_lp"]

            def child(i):
                r = self.roots[i]
                return ("first" if self.w.roles[r] else "variant", r, None, ())
        elif stage == "variant":
            lp = net.variant_prob(self.w, m, rid, prefix[0] if prefix else None)

            def child(i):
                t = m["menu"][m["families"][rid][i]]
                return (
                    "next" if len(self.w.roles[rid]) > len(prefix) else "emit",
                    rid,
                    t,
                    prefix,
                )
        else:
            lp = net.address(self.w, m, rid if stage == "first" else tid, prefix)

            def child(i):
                p = (*prefix, i)
                phase = (
                    "variant"
                    if stage == "first"
                    else "next"
                    if len(self.w.roles[rid]) > len(p)
                    else "emit"
                )
                return phase, rid, tid, p

        if lp is None:
            return None
        self.net_calls += 1
        p = lp.detach().double().exp().numpy()
        return p / p.sum(), child

    def draws(self, rng, budget, unique, end_probability=None):
        if not self.m.get("has_complete_domain", True):
            return []
        self.ended = False
        adjusted = {}
        logs = []
        root = ("root", None, None, ())
        for _ in range(budget):
            if end_probability is not None:
                if not 0 <= end_probability <= 1:
                    raise ValueError("invalid neural boundary probability")
                # END competes with the remaining mass of complete, named leaves.
                left = adjusted[root].sum() if root in adjusted else 1.0
                if left <= 0:
                    return logs
                total = end_probability + (1 - end_probability) * left
                if rng.random() * total < end_probability:
                    self.ended = True
                    return logs
            path = []
            key = root
            while key[0] != "emit":
                if key not in self.base:
                    self.base[key] = self.transition(key)
                if self.base[key] is None:
                    break
                base, child = self.base[key]
                weights = adjusted.get(key, base)
                cumulative = weights.cumsum()
                if cumulative[-1] == 0:
                    # All complete supported leaves below the root have been emitted.
                    assert key == root
                    return logs
                threshold = min(
                    rng.random() * cumulative[-1], np.nextafter(cumulative[-1], 0.0)
                )
                i = int(cumulative.searchsorted(threshold, side="right"))
                path.append((key, i))
                key = child(i)
            if key[0] != "emit":
                logs.append(None)
                continue
            logs.append((key[2], tuple(self.m["refs"][i] for i in key[3])))
            if unique:
                remaining = 0.0
                for parent, i in reversed(path):
                    base = self.base[parent][0]
                    if parent not in adjusted:
                        adjusted[parent] = base.copy()
                    # Absolute probability on the original edge times conditional remaining mass.
                    adjusted[parent][i] = base[i] * remaining
                    remaining = adjusted[parent].sum()
        return logs


class Policy:
    def __init__(self, net, unique=False):
        self.net = net
        self.unique = unique
        self.slots = self.calls = self.empty = 0

    def prepare(self, w):
        self.net.prepare(w)

    def generate(self, w, state, rng, slots):
        if not state["menu"]:
            return []
        page = Page(self.net, w, state)
        draws = page.draws(rng, slots, self.unique)
        self.slots += len(draws)
        self.calls += page.net_calls
        self.empty += draws.count(None)
        return [t for t in draws if t is not None]

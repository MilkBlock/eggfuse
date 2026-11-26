"""Intervene at one generation stage; keep historical Cell Stream scores on surviving paths."""

from time import perf_counter

import numpy as np
import torch

from discrete_reference import AnchorStream, Reference


class HybridStream(AnchorStream):
    def children(self, paths, depth, block):
        policy = self.hybrid
        if policy.stage == "rule" or (policy.stage == "later") != (depth > 0):
            yield from super().children(paths, depth, block)
            return
        # Build physical address-to-position maps only for the active Stream.
        # Anchor-restricted roles retain exactly their original domain/order.
        if depth not in self.positions:
            self.positions[depth] = {a: i for i, a in enumerate(self.roles[depth])}
            self.stats["hybrid_index_entries"] += len(self.positions[depth])
        parents = []
        cols = []
        for i, path in enumerate(paths.tolist()):
            root = self.roles[0][path[0]] if depth else None
            seqs = policy.proposals(self.rule, root, self.stats)
            prefix = tuple(self.roles[j][n] for j, n in enumerate(path))
            # Map the small set of network-produced full tails onto the existing
            # neural prefix cursor. Never enumerate candidate partners to find a proof.
            allowed = set()
            for seq in seqs:
                ordered = tuple(seq[j] for j in self.order) if depth else seq
                if ordered[:depth] == prefix:
                    col = self.positions[depth].get(ordered[depth])
                    if col is not None:
                        allowed.add(col)
            for col in sorted(allowed):
                parents.append(i)
                cols.append(col)
            if len(cols) >= block:
                yield torch.tensor(parents), torch.tensor(cols)
                parents, cols = [], []
        if cols:
            yield torch.tensor(parents), torch.tensor(cols)


class Hybrid(Reference):
    def __init__(self, m, marks, stage, draws):
        super().__init__(original_order=True)
        self.m, self.marks, self.stage, self.draws = m, marks, stage, draws
        self.rng = np.random.default_rng(536)
        self.inference = 0.0
        self.by_run = {}

    def proposals(self, rule, root, stats):
        key = (rule, root)
        if key not in self.sampled:
            named = (
                ((*root, self.m.pub.live[root][0]["version"]),)
                if root is not None
                else ()
            )
            seqs = []
            for _ in range(self.draws):
                c = self.marks.draw(
                    self.m,
                    self.rng,
                    stats,
                    oracle_key=(rule, False),
                    diagnostic_refs=named,
                    stop_after=1 if root is None else None,
                )
                if c is not None:
                    seqs.append(tuple(r[:2] for r in c.refs))
            self.sampled[key] = seqs
        return self.sampled[key]

    def scheduled_rules(self, frame, stats):
        if self.stage != "rule":
            return super().scheduled_rules(frame, stats)
        selected = set()
        for _ in range(self.draws):
            c = self.marks.draw(self.m, self.rng, stats, stop_after=0)
            if c is not None and not c.higher:
                selected.add(c.rule)
        return [(r, wm) for r, wm in frame["rules"] if r in selected]

    def make_stream(self, *args):
        rd, model, rule, wm, stats, order = args
        if order and order[0] != 0:
            raise ValueError("this staged experiment expects source slot zero first")
        stream = HybridStream(rd, model, rule, wm, stats, order=order)
        stream.hybrid = self
        stream.positions = {}
        return stream

    def run_snapshot(self, frame, pub, rd, model, txn, stats, deadline):
        rows, _, retired, accepted = pub
        changes = [
            (
                {"token": int(r[0]), "op": int(r[1])},
                rd.store.visible[int(r[0]), int(r[1])],
            )
            for r in rows
        ]
        self.m.update(
            {
                "updates": changes,
                "retired": [{"token": int(t), "op": int(o)} for t, o in retired],
                "rules": frame["rules"],
                "accepted": accepted,
            }
        )
        self.sampled = {}
        tick = perf_counter()
        super().run_snapshot(frame, pub, rd, model, txn, stats, deadline)
        self.inference += perf_counter() - tick
        self.by_run[frame["run"]] = self.inference

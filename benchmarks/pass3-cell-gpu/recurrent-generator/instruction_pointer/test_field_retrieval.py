import unittest
from itertools import product

import numpy as np
import torch

from composition_relation import Interfaces, Relation, Store
from field_retrieval import FieldEncoder, FieldIndex
from retrieval_panels import (
    compose_scores,
    domain_size,
    panels,
    parents,
    retrieve_owners,
    topk,
)


def change(t, values, version):
    return (
        {"token": t, "op": 0},
        {"table": 0, "hashes": values, "version": version, "forwarded": False},
    )


class StructuredReadTests(unittest.TestCase):
    def test_owner_budget_exposes_all_projections(self):
        owners = np.array([2, 3, 2, 4, 3])
        score = np.array([0.99, 0.71, 0.11, 0.60, 0.12])
        rows = retrieve_owners(score, np.arange(5), owners, np.zeros(5), limit=2)
        self.assertEqual(rows.tolist(), [0, 1, 4, 2])

    @torch.no_grad()
    def test_field_lifetime(self):
        index = FieldIndex(FieldEncoder(width=12))

        def advance(updates, retired=()):
            index.advance(dict(updates=updates, retired=retired))

        advance([change(-1, [9, 22], 1)])
        advance([change(-1, [9, 22], 2)])
        self.assertEqual((index.writes, index.removes), (2, 0))
        previous = index.keys[-1, 0][0].clone()
        advance([change(-1, [9, 27], 3)])
        self.assertEqual((index.writes, index.removes), (3, 1))
        torch.testing.assert_close(previous, index.keys[-1, 0][0])
        advance([], [{"token": -1, "op": 0}])
        self.assertFalse(index.rows or index.owners or index.buckets)
        self.assertEqual(index.writes, index.removes)

    @torch.no_grad()
    def test_blocked_domain_and_first_fresh_attribution(self):
        iface = Interfaces.__new__(Interfaces)
        iface.roles = [[("T", (0, 1)), ("T", (1, 0))]]
        iface.rules = [{"metadata": {"seminaive": True}}]
        iface.exports = {("initial", "T"): {0: "T"}}
        iface.tables = ["T"]
        store = Store(iface)
        updates = [change(-1, [3, 5], 1), change(-3, [5, 3], 3), change(-5, [5, 3], 3)]
        store.advance(dict(updates=updates, retired=[], accepted=[], repair_events=[]))
        model = Relation()
        events, budget = panels(store, model, 0, 3)
        tuples = [parents(a, i, b, j) for a, i, b, ix, _ in events for j in ix]
        expected = [
            r
            for r in product(store.visible, repeat=2)
            if any(store.visible[k]["version"] >= 3 for k in r)
        ]
        self.assertCountEqual(tuples, expected)
        self.assertEqual(domain_size(store, 0, 3), len(expected))
        self.assertEqual(budget, len(expected))
        for a, i, b, ix, _ in events:
            scores = compose_scores(a, i, b, ix)
            np.testing.assert_allclose(
                scores[:1], compose_scores(a, i, b, ix[:1]), atol=1e-5
            )
        self.assertEqual(topk(np.array([2, 1, 1]), np.arange(3), 2).tolist(), [0])

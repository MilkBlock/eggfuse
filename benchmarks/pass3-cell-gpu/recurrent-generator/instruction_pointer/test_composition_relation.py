import itertools
import unittest

import torch

from composition_relation import Interfaces, Relation, Store, encode
from relation_cases import request


class CellRelationTests(unittest.TestCase):
    def test_partitions_equal_brute_force(self):
        iface = Interfaces.__new__(Interfaces)
        iface.exports = {0: {0: "a", 1: "b"}, 1: {0: "b", 1: "c"}}
        for tables in itertools.product("abc", repeat=4):
            iface.roles = [[(table, ()) for table in tables]]
            iface.layouts.cache_clear()
            expected = set()
            for a, b in itertools.product(iface.exports.values(), repeat=2):
                for assignment in itertools.product(range(2), repeat=4):
                    if assignment[0] or not all(
                        t in (a, b)[j].values() for t, j in zip(tables, assignment)
                    ):
                        continue
                    expected.add(
                        tuple(
                            tuple(i for i, j in enumerate(assignment) if j == k)
                            for k in range(2)
                        )
                    )
            self.assertEqual(set(iface.layouts(0)), expected)

    def test_aligned_fields_and_stable_aliases(self):
        iface = Interfaces.__new__(Interfaces)
        iface.roles = [[("T", (0, 1)), ("T", (1, 0))]]
        iface.exports = {("initial", "T"): {0: "T"}}
        iface.tables = ["T"]
        store = Store(iface, rename_seed=55)

        def update(t, values):
            return (
                dict(token=t, op=0),
                dict(table=0, version=1, forwarded=False, hashes=values),
            )

        store.advance(
            dict(
                accepted=[],
                repair_events=[],
                retired=[],
                updates=[update(-1, [9, 5]), update(-3, [5, 9])],
            )
        )
        a, b = store.alias(-1), store.alias(-3)
        first = encode(store, 0, (0,), [((a, 0),)], 0, (1,))
        second = encode(store, 0, (1,), [((b, 0),)], 0, (0,))
        torch.testing.assert_close(first[1], second[1])
        model = Relation()
        q = model.vectors(*first, 0)
        k = model.vectors(*second, 1)
        expected = (
            model.q(model.encoder(first[0])) * model.k(model.encoder(second[0]))
        ).sum() + torch.nn.functional.softplus(model.scale).square()
        torch.testing.assert_close((q * k).sum(), expected)
        refs = request(1, 0, [(a, 0), (b, 0)], store)["parents"]
        self.assertEqual([r["address"]["token"] for r in refs], [-1, -3])

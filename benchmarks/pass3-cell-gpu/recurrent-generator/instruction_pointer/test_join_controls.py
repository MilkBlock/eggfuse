import unittest
from collections import Counter
from itertools import product

from compile_owner_study import pack
from composition_relation import Interfaces, Store
from join_controls import EqualityIndex, Generator


class TrackControlTests(unittest.TestCase):
    def test_shared_fields_against_full_product(self):
        iface = Interfaces.__new__(Interfaces)
        iface.tables = ["T"]
        iface.roles = [[("T", (0, 1)), ("T", (1, 0)), ("T", (0, 0))]]
        iface.rules = [{"metadata": {"seminaive": True}}]
        iface.exports = {("initial", "T"): {0: "T", 1: "T"}}
        gen = Generator.__new__(Generator)
        gen.arm = "A"
        gen.model = None
        gen.store = Store(iface)
        gen.index = EqualityIndex()
        gen.count, gen.times = Counter(), Counter()
        frame = dict(
            run=4, rules=[(0, 3)], accepted=[], retired=[], repair_events=[], updates=[]
        )
        for token, op, fields, version in [
            (-1, 0, [2, 1], 3),
            (-1, 1, [2, 2], 1),
            (-3, 0, [1, 2], 3),
            (-5, 0, [2, 2], 1),
            (-7, 0, [1, 1], 1),
        ]:
            frame["updates"].append(
                (
                    dict(token=token, op=op),
                    dict(table=0, hashes=fields, version=version),
                )
            )
        gen.advance(frame)
        actual = [
            tuple((a["address"]["token"], a["address"]["op"]) for a in q["parents"])
            for ps in gen.issue(frame).values()
            for q in ps
        ]
        expected = []
        for triple in product(gen.store.visible, repeat=3):
            if len({k[0] for k in triple}) > 2:
                continue
            rows = [gen.store.visible[k] for k in triple]
            if max(r["version"] for r in rows) < 3:
                continue
            (x, y), (b, c), (d, e) = [r["hashes"] for r in rows]
            if x == c == d == e and y == b:
                expected.append(triple)
        self.assertTrue(expected)
        self.assertCountEqual(actual, expected)

    def test_package_visible_only_after_end(self):
        def row(t, r, ps):
            return dict(
                token=t, run=r, parents=[dict(address=dict(token=p)) for p in ps]
            )

        refs = [
            row(1, 1, [-1]),
            row(2, 2, [1]),
            row(3, 2, [1, 2, -3]),
            row(4, 3, [1, 2, -3]),
        ]
        out = pack(refs, {"k": [(1, 2)]}, {"k"}, {3, 4})
        self.assertEqual(out["after"], {3: 1, 2: 1})
        self.assertEqual(out["unit_low"], 1)

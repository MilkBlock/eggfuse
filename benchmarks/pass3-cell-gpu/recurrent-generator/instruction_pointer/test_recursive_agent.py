import unittest
from collections import Counter, OrderedDict, defaultdict
from types import SimpleNamespace

from recursive_agent import Policy
from recursive_coverage import Target


class PendingTests(unittest.TestCase):
    def policy(self):
        p = Policy.__new__(Policy)
        p.reader = SimpleNamespace(
            store=SimpleNamespace(visible={(1, 0): {"version": 1}}), versions={2: 4}
        )
        p.next_table = lambda r, n: 2
        p.persistent = True
        p.pool = OrderedDict()
        p.closed = OrderedDict()
        p.wait = defaultdict(OrderedDict)
        p.ready = defaultdict(OrderedDict)
        p.active = defaultdict(OrderedDict)
        p.by_ref = defaultdict(set)
        p.count = Counter()
        return p

    def test_tried_survives_dormancy_and_new_evidence(self):
        p = self.policy()
        seq = ((1, 0),)
        tried = {((8, 1), 2)}
        for run in range(1, 5):
            p.save(9, seq, tried, run, 0.1)
        self.assertFalse(p.pool)
        p.save(9, seq, (), 5, 0.1)
        self.assertFalse(p.pool)
        p.reader.versions[2] += 1
        p.save(9, seq, (), 6, 0.1)
        key = next(iter(p.pool))
        self.assertEqual(p.pool[key].tried, tried)
        p.forget(key, "invalidated")
        self.assertFalse(p.by_ref)
        self.assertFalse(p.wait[2])
        self.assertFalse(p.active[9])

    def test_class_renaming_and_spurious_union(self):
        def row(name, n):
            return dict(table=name, subsumed=False, values=[{"sort": "S", "eq": n}])

        program = {
            "recipe": {
                "tables": [{"name": n, "kind": "constructor"} for n in ("A", "B")]
            }
        }
        target = Target(program, {"rows": [row("A", 1), row("B", 2)]})
        self.assertEqual(target.match({"rows": [row("A", 9), row("B", 8)]}), {0, 1})
        self.assertEqual(target.match({"rows": [row("A", 9), row("B", 9)]}), set())

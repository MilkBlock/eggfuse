"""Keep distinct legal bindings live when two entries share a trigger."""
import unittest

from multi_entry import check_types, paths_from_instance, resolve
from projected_entries import ProjectedEntries


class EntryContracts(unittest.TestCase):
    def setUp(self):
        self.rules = [
            {"inputs": [{"table": "Concat"}, {"table": "AddContext"}]},
            {"inputs": [{"table": "Concat"}], "outputs": {
                "2": {"table": "AddContext"}, "3": {"table": "Concat"}
            }}
        ]
        self.producer = {"parents": [{"address": {"token": 5464, "op": 7}, "version": 580}]}
        self.input = (5464, 7, 580)
        self.output = (5680, 3, 1044)
        self.trigger = (5680, 2, 1044)
        self.visible = {(t, pc): {"version": v} for t, pc, v in (self.input, self.output, self.trigger)}

    def test_same_event_distinct_entries_and_bindings(self):
        for first, expected in ((self.input, ("input", 0)), (self.output, ("return", 3))):
            parents = (first, self.trigger)
            path = paths_from_instance(parents, 1, self.producer)
            self.assertEqual(path, (expected, ("return", 2)))
            check_types(self.rules, 0, 1, 1, 2, path)
            self.assertEqual(resolve(path, 5680, [self.input], self.visible), parents)
        self.assertIsNone(paths_from_instance(((99, 7, 580), self.trigger), 1, self.producer))

    def test_absence_version_and_local_identity(self):
        path = (("input", 0), ("return", 2))
        self.assertIsNone(resolve(path, 5680, [(*self.input, 1)], self.visible))
        self.visible[self.input[:2]]["version"] += 1
        self.assertIsNone(resolve(path, 5680, [self.input], self.visible))
        del self.visible[self.output[:2]]
        self.assertIsNone(resolve((("return", 3), ("return", 2)), 5680, [], self.visible))

    def test_malformed_interface(self):
        for invalid in (("return", 2), ("input", -1), ("other", 0)):
            with self.assertRaises(ValueError):
                check_types(self.rules, 0, 1, 1, 2, (invalid, ("return", 2)))

    def test_contract_choice_preserves_body(self):
        lowering = ProjectedEntries.__new__(ProjectedEntries)
        key = (34, 1, 317, 2)
        lowering.routes = {key: [(28, {}), (29, {})]}
        lowering.preferred = ()
        self.assertEqual(lowering.route(key)[0], 28)
        lowering.preferred = (29,)
        self.assertEqual(lowering.route(key)[0], 29)
        self.assertIsNone(lowering.route(key, 99))

    def test_only_accepted_tuple_is_reserved(self):
        from collections import Counter, defaultdict
        from types import SimpleNamespace as NS
        from unittest.mock import Mock, patch
        import numpy as np

        p = ProjectedEntries.__new__(ProjectedEntries)
        key = (34, 1, 2, 2)
        p.routes = {key: [(28, {"reads": (("input", 0), ("return", 2))})]}
        p.preferred = ()
        p.root_rules = {0}
        p.choice = {0: 34}
        p.owners = {5680: [self.input]}
        p.count, p.done = Counter(), defaultdict(set)
        p.rules, p.covered_rules, p.covered_indices = {0: 1044}, {}, {}
        p.started, p.events, p.begin = {}, [], Mock()
        store = NS(types={5680: ("generated", 2)}, visible=self.visible)
        mem = NS(rd=NS(store=store, iface=NS(rules=[{"metadata": {"seminaive": True}}])),
                 bank=lambda _: NS(ports=[(5680, 2)]), roles=[["Concat", "AddContext"]])
        txn = NS(run=1045, capacity=8)
        with patch("projected_entries.send", side_effect=[
            np.array([[80, 12]]), np.array([[81, 0]])
        ]) as send:
            p.project_entries(0, 1, mem, txn)
            self.assertFalse(p.covered_rules)
            p.begin.assert_not_called()
            p.project_entries(0, 1, mem, txn)
            p.project_entries(0, 1, mem, txn)
        self.assertEqual(send.call_count, 2)
        self.assertEqual(p.covered_rules[0], {(self.input, self.trigger)})
        self.assertNotIn((self.output, self.trigger), p.covered_rules[0])
        p.begin.assert_called_once_with(34, (self.input, self.trigger), 81, txn)

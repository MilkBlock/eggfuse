import unittest
from collections import Counter
from types import SimpleNamespace
from unittest.mock import patch

from discrete_draft import Cell, Item, Local, valid
from region_owner import Instance, Ownership
from response_plan import ResponseMemory, ResponsePolicy, revise_references, split_draft


class TestResponsePlan(unittest.TestCase):
    def test_split_preserves_transitive_local_graph_and_ids(self):
        items = tuple(
            Item(i, Cell(r, refs))
            for i, r, refs in (
                (4, 10, ()),
                (1, 11, ()),
                (7, 12, (Local(4, 2),)),
                (2, 13, (Local(1, 0),)),
                (8, 14, ()),
            )
        )
        a, b = split_draft(items, {10, 11})
        self.assertEqual(([v.uid for v in a], [v.uid for v in b]), ([4], [1, 7, 2, 8]))
        pending = revise_references(b, lambda r: (19, 2, -1) if r == Local(4, 2) else r)
        self.assertTrue(valid(pending))
        self.assertEqual(split_draft(pending[1:], {12})[0], ())
        pinned = revise_references(
            pending, lambda r: (19, 2, 6) if r == (19, 2, -1) else r
        )
        self.assertEqual(split_draft(pinned[1:], {12})[0][0].cell.refs, ((19, 2, 6),))
        self.assertEqual(split_draft(items, {11}), ((), items))

    def test_unsigned_consumer_survives_acceptance_and_failed_producer(self):
        child = Item(11, Cell(2, (Local(7, 3),)))
        for status, expected in ((0, 81), (8, 0)):
            policy = ResponsePolicy.__new__(ResponsePolicy)
            policy.draft = (child,)
            with patch.object(Ownership, "issue", return_value={7: (81, status)}):
                policy.issue((Item(7, Cell(1, ())),), None, Counter())
            self.assertEqual(policy.draft[0].cell.refs, ((expected, 3, -1),))
            self.assertEqual(split_draft(policy.draft, {2})[0], ())

    def test_conditional_wire_keeps_native_guard_and_publication(self):
        contract = {
            "rules": [
                {
                    "outputs": {
                        "8": {
                            "table": 17,
                            "producer": "custom_merge",
                            "presence": "conditional",
                        }
                    }
                },
                {
                    "inputs": [{"table": 17}],
                    "query_conditions": "recipe.query",
                    "computations": [],
                },
            ],
            "availability": "after_publication",
            "lifetime": "resolve_version",
        }
        m = SimpleNamespace(contract=contract)
        unit = [(0, 0, []), (1, 1, [(0, 8)])]
        wire = ResponseMemory.wire_contract(m, unit, 1, 0)
        self.assertEqual(wire["source"]["presence"], "conditional")
        self.assertEqual(wire["query"], "recipe.query")
        self.assertEqual(wire["availability"], "after_publication")
        contract["rules"][1]["inputs"][0]["table"] = 18
        with self.assertRaises(ValueError):
            ResponseMemory.wire_contract(m, unit, 1, 0)

    def test_contract_uses_only_selected_producer_roles(self):
        m = SimpleNamespace(
            grouped=True,
            owner_rule={19: 0},
            projections=[{77: 4}],
            contract_cache={},
            roles=[(90, 77, 77, 52)],
        )
        self.assertEqual(ResponseMemory.owner_contract(m, 0, (19, 5, 3)), {1: 4, 2: 4})
        self.assertEqual(ResponseMemory.owner_contract(m, 0, (20, 5, 3)), {})
        self.assertEqual(ResponseMemory.owner_contract(m, 0, Local(19, 5)), {})

    def test_pinned_retirement_releases_and_unpublished_output_waits(self):
        for ver, expected in ((3, 0), (None, 1)):
            # A real acceptance can exist with no corresponding publication yet.
            inst = Instance([(1, 0, []), (2, 1, [(0, 3)])], (), owners=[7])
            if ver is not None:
                inst.versions[7, 3] = ver
            events = []
            policy = SimpleNamespace(
                waiting=[inst],
                watch={},
                owned={},
                confirmed=SimpleNamespace(live={}),
                record_boundary=lambda *args: events.append(args[-2]),
                close=lambda i: None,
            )
            Ownership.resume_programs(
                policy, {"rules": [(2, 0)]}, ([], [], [], []), None, Counter()
            )
            self.assertEqual(len(policy.waiting), expected)
            self.assertEqual(events, ["invalidated" if ver else "await_publication"])


if __name__ == "__main__":
    unittest.main()

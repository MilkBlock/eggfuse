"""Exercise typed late binding, immutable prefix reuse and recursive publication."""
from collections import Counter, defaultdict
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import patch

import numpy as np

from recursive_ripsat import OpenEntries, compile_boundary
from recursive_ripsat_study import reward


class RecursiveRipSat(TestCase):
    def setUp(self):
        self.p = OpenEntries.__new__(OpenEntries)
        self.p.rules = {0: 1}
        self.p.done = defaultdict(set)
        self.p.covered_indices, self.p.covered_rules = {}, {}
        self.p.suffix_tokens, self.p.suffix_positions = {}, defaultdict(set)
        self.p.publish_next, self.p.lineage = [], []
        self.p.recent = defaultdict(dict)
        self.p.open_ports = {(8, 1, 2): 1, (9, 0, 2): 2}
        self.p.txn = NS(run=4)
        self.p.count = Counter()
        self.p.exports, self.plans = compile_boundary([dict(
            inputs=[dict(table=5), dict(table=6)],
            outputs={"2": dict(table=7), "3": dict(table=8)})])
        self.refs = ((8, 1, 2), (9, 0, 2))
        visible = {(t, op): {"version": v} for t, op, v in self.refs}
        self.rd = NS(store=NS(visible=visible), iface=NS(rules=[{"metadata": {"seminaive": True}}]))
        self.mem = NS(rd=self.rd, roles=[(5, 6)], bank=lambda _: NS(positions={(8, 1): 0, (9, 0): 1}))

    def test_contract_needs_one_typed_operand_and_accepts_different_owners(self):
        self.assertEqual(self.plans[0, 0].remaining, ((1, 6),))
        self.assertEqual(self.plans[0, 1].remaining, ((0, 5),))
        with patch("recursive_ripsat.send", return_value=np.array([[30, 0]])) as send:
            self.p.issue_suffix(0, self.refs, "Compose", self.mem)
            self.p.issue_suffix(0, self.refs, "Compose", self.mem)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.args[2].tolist(), [[list(p) for p in self.refs]])
        self.assertEqual(self.p.publish_next, [(30, 0, 3, (8, 9))])
        self.assertNotIn((30, 2, 4), self.p.open_ports)
        self.rd.store.visible[30, 2] = {"version": 4, "table": 7}
        self.p.publish(self.rd, *self.p.publish_next[0])
        self.assertEqual(self.p.open_ports[30, 2, 4], 3)
        self.assertFalse(self.p.recent[8])  # conditional port never returned
        self.p.txn.run = 5
        self.p.done.clear()
        self.p.rules[0] = 5
        with patch("recursive_ripsat.send") as send:
            self.p.issue_suffix(0, self.refs, "Compose", self.mem)
            send.assert_not_called()

    def test_stale_or_retired_operand_never_replays_prefix(self):
        with patch("recursive_ripsat.send") as send:
            self.rd.store.visible[8, 1]["version"] += 1
            self.p.issue_suffix(0, self.refs, "Compose", self.mem)
            del self.rd.store.visible[8, 1]
            self.p.issue_suffix(0, self.refs, "Compose", self.mem)
            send.assert_not_called()
        self.assertFalse(self.p.publish_next)

    def test_two_ports_from_one_instance_cannot_compose_it_with_itself(self):
        self.p.open_ports[8, 2, 2] = 1
        with patch("recursive_ripsat.send") as send:
            self.p.issue_suffix(0, (self.refs[0], (8, 2, 2)), "Compose", self.mem)
            send.assert_not_called()

    def test_rejection_cannot_mark_completion(self):
        self.p.open_ports.pop(self.refs[1])
        with patch("recursive_ripsat.send", return_value=np.array([[30, 9]])) as send:
            self.p.issue_suffix(0, self.refs, "Extend", self.mem)
        send.assert_called_once()
        self.assertFalse(self.p.done[0])
        self.assertFalse(self.p.suffix_tokens)
        self.assertFalse(self.p.publish_next)

    def test_cheap_incomplete_policy_loses(self):
        baseline = dict(facts=15, signed_ops=23, charged_with_decisions=100, wall=3.)
        self.assertLess(reward(dict(baseline, facts=14, wall=.01, charged_with_decisions=1), baseline),
                        reward(baseline, baseline))

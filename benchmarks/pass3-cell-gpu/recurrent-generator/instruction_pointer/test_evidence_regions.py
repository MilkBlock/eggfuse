from collections import Counter, defaultdict
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import Mock, patch

import numpy as np

from evidence_execution import EvidenceEntries, Region
from evidence_regions import OUTPUT, PARTNER, grow


def named_arg(token):
    return {"address": {"token": token, "op": 0}, "version": 1}


class EvidenceRegionTests(TestCase):
    def test_shared_evidence_branches_converge_after_publication_and_stop_at_external_obligation(self):
        # Two sibling rules consume the same independent pair. A third consumer
        # needs an unbound third event. Only the signed siblings can feed the merge.
        parents = {10: [1, 2], 11: [1, 2], 12: [1, 2, 3], 13: [10, 11], 14: [13]}
        runs = {10: 2, 11: 2, 12: 2, 13: 3, 14: 5}
        q = {t: {"rule": t, "run": runs[t], "parents": list(map(named_arg, ps))} for t, ps in parents.items()}
        schedule = {r: [run] for r, run in runs.items()}
        schedule[14] = [4, 5]  # A replay-only later success cannot certify the earlier attempt.
        e = NS(
            t=NS(
                q=q,
                schedule=schedule,
                rules=NS(rules={r: {"outputs": {"0": {}}} for r in runs}),
                snap=NS(version=lambda *a: 1),
            ),
            sigs={t: str(t) for t in q},
            uses=defaultdict(list, {10: [(3, 13)], 11: [(3, 13)], 13: [(5, 14)]}),
        )
        start = {(1, 0, 1): (OUTPUT, 0)}
        jobs = [(2, 10), (2, 11), (2, 12)]
        self.assertEqual(grow(e, 2, 1, start, jobs), ((), ()))
        plan, ts = grow(e, 2, 1, start, jobs, (2, 0, 1))
        self.assertEqual(ts, (10, 11, 13))
        self.assertEqual(plan[0][1], ((OUTPUT, 0), (PARTNER, 0)))
        self.assertEqual(plan[1][1], plan[0][1])
        self.assertEqual(plan[2][1], ((0, 0), (1, 0)))

    def test_skip_binary_root_only_after_entire_live_posting_is_proved(self):
        p = EvidenceEntries.__new__(EvidenceEntries)
        p.count = Counter()
        p.prefixes = {(1, 0): {4: {5, 6}, 8: {9}}}
        mem = Mock()
        mem.window.return_value = np.array([5, 6, 9, 10]), [0, 2], [2, 2]
        kept = p.remaining_binary_roots(mem, 1, (0, 1), np.array([2, 4, 8]))
        self.assertEqual(kept.tolist(), [2, 8])
        self.assertEqual(p.count["evidence_binary_root_scores_skipped"], 1)
        self.assertEqual(p.count["evidence_certified_leaf_scores_skipped"], 2)

    @patch("evidence_execution.send")
    def test_absent_conditional_output_only_closes_its_own_branch(self, send):
        p = EvidenceEntries.__new__(EvidenceEntries)
        p.count = Counter()
        p.regions = {0: ((1, ((OUTPUT, 0),)), (2, ((0, 1),)), (3, ((0, 2),)))}
        p.txn = NS(run=3)
        p.rules = {2: 3, 3: 3}
        p.done = defaultdict(set)
        p.covered_rules, p.covered_indices = {}, {}
        p.suffix_positions, p.struct_positions = defaultdict(set), defaultdict(dict)
        p.active, p.publish_next, p.suffix_tokens = [], [], {}
        p.just_published = set()
        region = Region(0, 99, 1, {}, tokens={0: 10})
        mem = Mock()
        mem.rd.iface.rules = [{"metadata": {"seminaive": True}}] * 4
        mem.roles = {2: (1,), 3: (1,)}
        mem.rd.store.visible = {(10, 2): {"table": 1, "version": 3}}
        mem.bank.return_value.positions = {(10, 2): 1}
        p.advance_region(region, mem)
        send.assert_not_called()
        self.assertEqual(p.active, [region])
        p.just_published = {10}
        send.return_value = np.array([[28, 0]])
        p.advance_region(region, mem)
        self.assertEqual(region.tokens, {0: 10, 1: None, 2: 28})
        self.assertEqual(region.vertical, 1)
        self.assertEqual(p.done[2], set())
        self.assertEqual(p.done[3], {((10, 2, 3),)})

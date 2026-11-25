import unittest
from collections import Counter, defaultdict
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from region_owner import Instance, Ownership


class OwnershipTest(unittest.TestCase):
    def setUp(self):
        self.m = SimpleNamespace(pub=SimpleNamespace(live={}), rows=defaultdict(list), last=None)
        self.p = Ownership(self.m, None, None, "noop", 1, 1, 1)
        self.w = Counter()
        self.frame = {"rules": [(1, 0), (2, 0)]}
        self.unit = [(0, 0, [(-1, 0)]), (1, 1, [(0, 2)]), (2, 2, [(0, 3), (1, 0)])]
        self.instance = Instance(self.unit, ((1, 0, 2),))
        self.p.attach(self.instance, 8, self.w)
        self.p.waiting.append(self.instance)

    def publish(self, rows, rules=None):
        for t, op, v in rows:
            self.m.pub.live[t, op] = ({"version": v}, None)
        self.p.resume_programs(
            self.frame if rules is None else {"rules": rules}, (rows, [], [], []), None, self.w
        )

    @patch("region_owner.send")
    def test_early_publication_pinned_while_blocked_and_stale(self, send):
        send.return_value = np.array([[9, 0]])
        self.publish([(8, 3, 4)])
        self.assertEqual(self.w["blocked_waits"], 1)
        self.publish([(8, 2, 6), (8, 3, 5)])
        self.publish([(9, 0, 1)])
        self.assertEqual(send.call_count, 1)
        self.assertFalse(self.p.waiting)
        self.assertFalse(self.p.watch)
        self.assertEqual(self.w["stale_released"], 1)

    @patch("region_owner.send")
    def test_rejection_releases_unpublished_watches(self, send):
        send.return_value = np.array([[7, 1]])
        self.publish([(8, 2, 1)])
        self.assertFalse(self.p.waiting)
        self.assertFalse(self.p.owned)
        self.assertFalse(self.p.watch)
        self.assertEqual(self.w["suffix_rejected"], 1)

    @patch("region_owner.send")
    def test_waits_for_schedule_and_published_version(self, send):
        send.side_effect = [np.array([[11, 0]]), np.array([[12, 0]])]
        self.publish([(8, 2, 8), (8, 3, 2)], [])
        self.assertFalse(send.called)
        self.publish([])
        self.publish([])
        self.assertEqual(send.call_count, 1)
        self.publish([(11, 0, 4)])
        self.assertEqual(self.w["higher_completed"], 1)
        self.assertEqual(send.call_args.args[2].tolist(), [[[8, 3, 2], [11, 0, 4]]])

    @patch("region_owner.send")
    def test_external_wait_preserves_original_reference_and_paid_work(self, send):
        unit = [(7, 0, [(-1, 0)]), (1, 1, [(-1, 0)])]
        inst = Instance(unit, ((44, 3, 5),), [8])
        self.p.waiting = [inst]
        self.publish([(45, 3, 5)])
        self.assertFalse(send.called)
        self.assertEqual(self.p.waiting, [inst])
        send.return_value = np.array([[9, 0]])
        self.publish([(44, 3, 5)])
        self.assertEqual(send.call_count, 1)
        self.publish([])
        self.assertFalse(self.p.owned)
        self.assertFalse(self.p.waiting)

    def test_neural_shortcut_is_single_physical_leaf_only(self):
        rng = np.random.default_rng(3)
        self.m.rows[4] = [(8, 1)]
        self.m.pub.live[8, 1] = ({"version": 7}, None)
        self.p.owned[3, ((8, 1, 6),)] = (9, 0)
        self.assertIsNone(self.p.forced_owned(3, 4, None, rng, self.w))
        self.p.owned[3, ((8, 1, 7),)] = (10, 0)
        self.assertEqual(self.p.forced_owned(3, 4, None, rng, self.w).refs, ((8, 1, 7),))
        self.m.rows[4].append((9, 1))
        self.assertIsNone(self.p.forced_owned(3, 4, None, rng, self.w))


if __name__ == "__main__":
    unittest.main()

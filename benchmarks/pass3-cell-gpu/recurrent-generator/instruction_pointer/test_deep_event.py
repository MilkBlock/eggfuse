import unittest
from collections import Counter, defaultdict
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from deep_ripsat import depth
from deep_event_boundary import FullTemplates


class DeepBakeTests(unittest.TestCase):
    def test_depth_distinguishes_fanout_from_chain(self):
        root = (0, 0, ())
        child = (1, 1, ((0, 0),))
        self.assertEqual(depth([root, child, child]), 2)
        self.assertEqual(depth([root, child, (2, 2, ((1, 0),))]), 3)

    def test_group_requires_every_rule_and_uses_actual_version(self):
        policy = FullTemplates.__new__(FullTemplates)
        policy.cat = SimpleNamespace(
            units={0: [(0, 0, ()), (1, 1, ((0, 2),)), (2, 1, ((0, 2),))]}
        )
        policy.rules = {1: 0}
        policy.waiting, policy.expected = [], set()
        policy.count, policy.done = Counter(), defaultdict(set)
        ports = {(0, 2): (100, 2, 61)}
        with patch("deep_event_boundary.send") as send:
            policy.group(0, {}, [100], ports, 1, None)
            send.assert_not_called()
            policy.rules[2] = 0
            send.side_effect = [np.array([[101, 0]]), np.array([[102, 0]])]
            policy.group(*policy.waiting.pop(), None)
            self.assertEqual([call.args[1] for call in send.call_args_list], [1, 2])
            for call in send.call_args_list:
                np.testing.assert_array_equal(call.args[2], [[[100, 2, 61]]])
            self.assertEqual(policy.expected, {101, 102})

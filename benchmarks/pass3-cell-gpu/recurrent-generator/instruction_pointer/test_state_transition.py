import unittest
from collections import Counter
from types import SimpleNamespace
from unittest.mock import patch

from cell_kv_runtime import Instances
from state_transition_corpus import Replay
from state_transition_live import SlotBudget
from state_transition_measure import groups


class TransitionTests(unittest.TestCase):
    def test_slot_limit_charges_unused_reserved_slots_and_resets_per_execution(self):
        policy = SlotBudget(None, True, 8)
        with patch("competition_draw.Policy.generate", return_value=[]) as gen:
            for s in ({"menu": []}, {"menu": [1]}, {"menu": [1]}, {"menu": [1]}):
                policy.generate(None, s, None, 6)
            self.assertEqual([c.args[-1] for c in gen.call_args_list], [6, 2])
            self.assertEqual(policy.offered, 8)

    def test_exhausted_paid_budget_retains_pending_suffix(self):
        w = SimpleNamespace(layouts=[[(0, 0, []), (1, 1, [(0, 0)])]])
        mem = Instances(w)
        pending = [(3, 0, [3])]
        self.assertEqual(
            mem.suffix(w, None, {1: True}, pending, Counter(paid=7), 7), pending
        )

    def test_no_credit_for_expiry_or_partial_overlap(self):
        t = ((2, ()), (3, ()), (4, ()))

        def rec(gain):
            return {"gain": gain, "positive": True}

        before = {
            "labels": {t[0]: rec((1,)), t[1]: rec((1, 2)), t[2]: rec((3,))},
            "baseline": set(),
        }
        after = {"labels": {t[2]: rec((3,))}, "baseline": {1}}
        gs = groups(before, after, 4)
        self.assertEqual(gs["completed"], {t[0]})
        self.assertEqual(gs["persistent"], {t[2]})
        self.assertEqual(gs["other_lost"], {t[1]})

    def test_prefix_replay_requires_identical_named_state(self):
        policy = Replay([({"epoch": 9}, [(0, ())], [])], [])
        with self.assertRaises(ValueError):
            policy.generate(None, {"epoch": 10}, None, 1)

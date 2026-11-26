import unittest
from collections import defaultdict

from experience_labels import select_runs


class StateSelectionTests(unittest.TestCase):
    def test_first_gap_and_repeat_are_retained_with_fixed_sampling(self):
        pages = [
            {"run": r, "page": 0, "generated": [r, r] if r == 29 else []}
            for r in range(1, 31)
        ]
        pages.append({"run": 30, "page": 1, "generated": [1] * 100})
        executed = defaultdict(list, {2: [1], 4: [2]})
        selected = select_runs(pages, executed)
        self.assertEqual(selected, select_runs(pages, executed))
        self.assertIn("first_gap", selected[3])
        self.assertIn("repeat", selected[29])
        self.assertNotIn("repeat", selected.get(30, ()))

    def test_no_success_keeps_idle_states_without_fabricating_first_gap(self):
        pages = [{"run": 7, "page": 0, "generated": []}]
        self.assertIn("idle", select_runs(pages, defaultdict(list))[7])
        self.assertNotIn("first_gap", select_runs(pages, defaultdict(list))[7])

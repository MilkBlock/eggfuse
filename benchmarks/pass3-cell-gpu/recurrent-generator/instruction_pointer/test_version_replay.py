"""Regression cases for unmaterialized, revised, retired and aliased ports."""

import unittest
from collections import defaultdict

from version_causes import classify
from version_expand import shrink
from version_replay import compile_dag, record_publication


def frame(run, version=None, retired=False):
    addr = dict(token=1, op=2)
    return dict(
        run=run,
        retired=[addr] if retired else [],
        updates=[] if version is None else [[addr, dict(version=version)]],
    )


def consumer(run, version):
    return dict(
        token=3, run=run, parents=[dict(address=dict(token=1, op=2), version=version)]
    )


class VersionTests(unittest.TestCase):
    def test_bind_to_actual_revision(self):
        rows = [frame(1), frame(2, 1), frame(3, 1), frame(4, 3)]
        self.assertEqual(compile_dag([consumer(4, 3)], rows), {3: [(1, 2, 2)]})
        with self.assertRaises(ValueError):
            compile_dag([consumer(4, 1)], rows)

    def test_retirement_is_not_a_live_receipt(self):
        rows = [frame(1, 0), frame(2, retired=True)]
        with self.assertRaises(ValueError):
            compile_dag([consumer(2, 0)], rows)
        self.assertEqual(
            compile_dag([consumer(3, 0)], rows + [frame(3, 0)]), {3: [(1, 2, 2)]}
        )

    def test_shared_owner_separate_operations(self):
        live = {}
        h = defaultdict(list)
        for op in (1, 2, 2):
            record_publication(live, h, (7, op), 4)
        record_publication(live, h, (7, 1), 6)
        self.assertEqual(h, {(7, 1): [4, 6], (7, 2): [4]})

    def test_classification_uses_both_ablation_directions(self):
        self.assertEqual(classify(False, True, False), "outside_sufficient")
        self.assertEqual(classify(True, True, False), "both_sufficient_alternatives")
        self.assertEqual(classify(False, False, False), "mixed_required")

    def test_sufficient_subsets_can_require_two_writers(self):
        self.assertEqual(shrink({1, 2, 3}, lambda s: {1, 3} <= s), {1, 3})
        with self.assertRaises(ValueError):
            shrink({1, 2}, lambda s: 3 in s)


if __name__ == "__main__":
    unittest.main()

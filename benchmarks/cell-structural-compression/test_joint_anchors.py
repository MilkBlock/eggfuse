import unittest
from analyze_joint_anchors import extra_ports


class JointAnchorTests(unittest.TestCase):
    def test_duplicate_and_overlapping_symbols_count_once(self):
        self.assertEqual(extra_ports([[{1,2}, {1,2}]]), 0)
        self.assertEqual(extra_ports([[{1,2}, {2,3}]]), 1)

    def test_separate_components_are_alternatives_not_a_union(self):
        self.assertEqual(extra_ports([[{1,2}], [{3,4}]]), 0)
        self.assertEqual(extra_ports([[{1},{2}], [{3},{4},{5}]]), 2)

    def test_empty_evidence_never_establishes_sharing(self):
        self.assertEqual(extra_ports([]), 0)
        self.assertEqual(extra_ports([[set(),set()]]), 0)


if __name__ == '__main__': unittest.main()

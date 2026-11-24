import unittest

import torch

from joint_slots import JointSlots


class JointLossTests(unittest.TestCase):
    def test_empty_template_and_training_set_permutation(self):
        from train_joint_slots import loss
        head = JointSlots(8, 3)
        scores, stop = head(torch.ones(8), [], [], [], [], [], 2)
        self.assertEqual(scores, [])
        self.assertEqual(stop.shape, (3,))
        scores = [torch.randn(3, 4), torch.randn(3, 5)]
        targets = [[1, 3], [2, 0]]
        original = loss(scores, stop, targets)
        torch.testing.assert_close(original, loss(scores, stop, list(reversed(targets))))
        shuffle = [2, 0, 1]
        torch.testing.assert_close(original, loss([s[shuffle] for s in scores],stop[shuffle], targets))

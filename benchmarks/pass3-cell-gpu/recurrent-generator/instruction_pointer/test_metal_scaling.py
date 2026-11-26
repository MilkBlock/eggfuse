import unittest

import torch

from metal_scaling import SIZES, models, objective


class MetalScaling(unittest.TestCase):
    def test_capacity_and_interface(self):
        # Meta device checks the largest shapes without reserving model storage.
        with torch.device("meta"):
            for size, target in SIZES.items():
                marks, rates = models(size)
                count = sum(
                    p.numel() for net in (marks, rates) for p in net.parameters()
                )
                if target:
                    self.assertLess(abs(count / target - 1), 0.05)
                else:
                    self.assertEqual(count, 15732)
                self.assertEqual(marks.choice(torch.zeros(4, 99)).shape, (4, 1))
                self.assertEqual(rates(torch.zeros(4, 166)).shape, (4, 3))

    def test_invalid_terminal_edit_sites_do_not_affect_objective(self):
        x = torch.zeros(1, 166)
        y = torch.tensor([[1.0, 0.0, 0.0]])

        class Last(torch.nn.Module):
            def forward(self, rows):
                return rows[:, -3:]

        before, _ = objective(Last(), (x, y), "rate")
        x[0, -2:] = 30
        after, _ = objective(Last(), (x, y), "rate")
        self.assertEqual(before, after)

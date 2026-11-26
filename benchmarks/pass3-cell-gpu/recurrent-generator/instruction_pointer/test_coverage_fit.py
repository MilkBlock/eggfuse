import itertools
import unittest

import torch

from coverage_fit import expected_distinct
from coverage_onpolicy import coefficients


class CoverageLossTests(unittest.TestCase):
    def test_distinct_matches_exhaustive_two_draws(self):
        # a and b are verified addresses of one contribution; u has no label.
        draws = {"a": 0.2, "b": 0.1, "c": 0.3, "u": 0.4}
        sig = {"a": 1, "b": 1, "c": 2}
        exact = sum(
            p * q * len({sig[v] for v in (i, j) if v in sig})
            for i, p in draws.items()
            for j, q in draws.items()
        )
        groups = torch.tensor(
            [draws["a"] + draws["b"], draws["c"]], dtype=torch.float64
        )
        self.assertAlmostEqual(expected_distinct(groups, 2).sum().item(), exact)

    def test_finite_at_endpoints_and_rare_gradients(self):
        p = torch.tensor([0.0, 1e-12, 0.05, 0.25, 1.0], requires_grad=True)
        value = expected_distinct(p, 256)
        value.sum().backward()
        self.assertTrue(torch.isfinite(p.grad).all())
        self.assertGreater(value[1].item(), 0)
        self.assertGreater(p.grad[2].item(), p.grad[3].item())
        self.assertEqual(value[-1].item(), 1)

    def test_complete_budget_divides_out_construction_failures(self):
        # Includes a multi-op root represented by both Higher and Primitive.
        mass = torch.tensor([0.01 + 0.02, 0.04])
        other_mass = 0.03
        expected = expected_distinct(mass / (mass.sum() + other_mass), 4).sum()
        self.assertAlmostEqual(float(expected), 2 - 0.7**4 - 0.6**4, places=6)

    def test_paired_score_is_gradient_of_exact_conditional_coverage(self):
        # Two addresses are aliases; a third is unknown and a fourth cannot form a token.
        logits = torch.tensor(
            [-0.2, 0.7, 0.3, 1.5], dtype=torch.float64, requires_grad=True
        )
        raw = logits.softmax(0)
        q = raw[:3] / raw[:3].sum()
        target = expected_distinct(q[:2].sum(), 2)
        true_gradient = torch.autograd.grad(target, logits, retain_graph=True)[0]
        surrogate = 0
        for xs in itertools.product(range(3), repeat=4):
            coeff = coefficients(xs[:2], xs[2:], {0: "same", 1: "same"})
            weight = q[list(xs)].prod().detach()
            surrogate += weight * sum(v * raw[c].log() for c, v in coeff.items()) / 2
        torch.testing.assert_close(
            torch.autograd.grad(surrogate, logits)[0], true_gradient
        )

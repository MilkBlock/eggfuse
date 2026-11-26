import random
import unittest
from collections import Counter
from types import SimpleNamespace

from discovery_sampling import Domain


class PhysicalControlTests(unittest.TestCase):
    def setUp(self):
        live = {
            (10, 1): ({"table": 0, "version": 3}, None),
            (20, 2): ({"table": 0, "version": 7}, None),
        }
        m = SimpleNamespace(
            pub=SimpleNamespace(live=live),
            ids=[(0, False), (1, False), (1, True), (2, False)],
            roles=[[], [0, 0], [1]],
        )
        self.domain = Domain(m)

    def test_rank_support_and_versions(self):
        d = self.domain
        cells = [d.decode(i) for i in range(d.size)]
        self.assertEqual(len(set(cells)), 9)
        self.assertEqual(
            Counter((c.rule, c.higher) for c in cells),
            {(0, False): 1, (1, False): 4, (1, True): 4},
        )
        self.assertTrue(
            all(p in ((10, 1, 3), (20, 2, 7)) for c in cells for p in c.refs)
        )

    def test_sparse_shuffle_exhausts_without_repetition(self):
        d = self.domain
        expected = {d.decode(i) for i in range(d.size)}
        for seed in range(100):
            samples = list(d.draw("unique", random.Random(seed), 100))
            self.assertEqual(len(samples), len(expected))
            self.assertEqual(set(samples), expected)

    def test_uniform_template_and_uniform_token_are_different_controls(self):
        for arm, expected in (("uniform", 1 / 9), ("factored", 1 / 3)):
            samples = self.domain.draw(arm, random.Random(91), 10000)
            self.assertAlmostEqual(
                sum(c.rule == 0 for c in samples) / 10000, expected, delta=0.02
            )

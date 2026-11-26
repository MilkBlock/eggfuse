import unittest

import numpy as np
import torch
from torch import nn

from address_diagnosis import leaf_scores, route_trace
from address_example import explain
from address_scores import cluster, init_w, tree


class AddressTests(unittest.TestCase):
    def test_uneven_split_visits_target(self):
        for n in (1, 2, 3, 7, 1024, 1025):
            keys = list(range(n))
            _, _, _, _, mask, _ = tree(n)
            for i in (0, n // 2, n - 1):
                path = explain(keys, i, [0.5] * sum(mask[i]))
                self.assertEqual(len(path), sum(mask[i]))

    @unittest.skipUnless(torch.backends.mps.is_available(), "Metal required")
    def test_binary_routes_and_softmax_are_normalized(self):
        rng = np.random.default_rng(291)
        q = rng.normal(size=(5, 32)).astype("float32")
        k = rng.normal(size=(17, 32)).astype("float32")
        w = init_w().to("mps")
        net = nn.Linear(99, 1).to("mps")
        for arm in ("original", "tree-dot", "direct-dot", "semantic-mlp"):
            with torch.no_grad():
                p, br = leaf_scores(q, k, 0, arm, net, w)
            np.testing.assert_allclose(p.sum(1), 1, atol=1e-6)
            if arm == "original":
                for j in range(len(k)):
                    self.assertAlmostEqual(
                        p[2, j], np.prod(route_trace(len(k), j, br, 2))
                    )

    def test_centroids_include_nonpivot_leaf(self):
        k = torch.arange(32, dtype=torch.float32).expand(1024, -1).clone()
        _order, l, r = cluster(k)
        k[1, 0] += 2
        _, ll, rr = cluster(k)
        # Modifying a nonpivot cannot affect the physical top pair but contributes to a centroid.
        self.assertEqual(tree(1024)[0][0], 255)
        self.assertEqual(tree(1024)[1][0], 767)
        self.assertGreater((ll[0] - l[0]).abs().sum() + (rr[0] - r[0]).abs().sum(), 0)

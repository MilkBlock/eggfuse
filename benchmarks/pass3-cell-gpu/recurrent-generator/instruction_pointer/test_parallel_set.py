import unittest

import numpy as np
import torch

from discrete_draft import Cell
from parallel_budget import bounds
from parallel_fit import align, coupled, site_features
from parallel_memory import scalars
from parallel_page import library


class SetTests(unittest.TestCase):
    def test_alignment_preserves_common_and_counts_twins_once(self):
        src = ["c", "a", "a", None]
        for seed in range(25):
            end = align(src, ["b", "c", "a"], np.random.default_rng(seed))
            self.assertEqual(end[0], "c")
            self.assertIn("a", end[1:3])
            self.assertCountEqual(end, ["a", "b", "c", None])
            for t in (0, 1):
                cur, target = coupled(
                    src, ["b", "c", "a"], t, np.random.default_rng(seed)
                )
                self.assertEqual(cur, src if t == 0 else target)

    def test_pool_is_equivariant_and_exposes_siblings(self):
        z = torch.zeros(32)
        vec = torch.arange(128).reshape(4, 32).float()
        live = torch.tensor([1.0, 0.0, 1.0, 0.0])
        p = [2, 1, 3, 0]
        x, h = site_features(z, z, vec, live, 0.25)
        y, g = site_features(z, z, vec[p], live[p], 0.25)
        torch.testing.assert_close(x[p], y)
        torch.testing.assert_close(g, h)
        self.assertGreater(
            (x[1] - site_features(z, z, vec, torch.zeros_like(live), 0.25)[0][1])
            .abs()
            .sum(),
            0,
        )

    def test_budget_under_shared_first_parent(self):
        group = [Cell(r, ((1, 2, 3), (i, 2, 4))) for r in range(5) for i in range(6)]
        self.assertEqual(
            bounds(group + group),
            {
                "rules": 5,
                "bindings": 30,
                "rule4": 24,
                "four_rules_four_complete": 16,
                "first4": 30,
                "later4": 20,
                "cascade4": 16,
            },
        )

    def test_compute_roles_are_shared_and_unbound_values_excluded(self):
        rule = {
            "inputs": [{"atom": 8}],
            "computations": [
                {
                    "atom": 4,
                    "operands": [
                        {"fields": [[8, 1]]},
                        {"literal_operand": 0},
                        {"fields": [[8, 0]]},
                    ],
                },
                {"atom": 5, "operands": [{"fields": []}]},
            ],
        }
        (d,) = scalars(3, rule)
        self.assertEqual((d.rule, d.atom, d.roles), (3, 4, (0,)))
        self.assertEqual(
            d.wire([(17, 2, 23)]), [(17, 2, 23, 1), (0, -1, 0, 0), (17, 2, 23, 0)]
        )

    @unittest.skipUnless(torch.backends.mps.is_available(), "Metal required")
    def test_device_keeps_and_deletes_only_occupied_slots(self):
        lib = library(48)

        def jobs(logits, method, n):
            ctl = torch.tensor([n] + [0] * 15, device="mps", dtype=torch.int32)
            job = torch.zeros((8, 2), device="mps", dtype=torch.int32)
            cfg = torch.tensor(
                [4, 1, 1, 1, 1, 1, 1, 0, 32, 0, 48, 8], device="mps", dtype=torch.int32
            )
            settings = torch.tensor([method, 1], device="mps", dtype=torch.int32)
            lib.set_jobs(
                torch.tensor(logits, device="mps").float().repeat(4, 1),
                ctl,
                job,
                cfg,
                settings,
                threads=1,
            )
            rows = job.cpu().tolist()
            return rows[: int(ctl.cpu()[3])]

        self.assertEqual(jobs([50, -50, -50], 2, 2), [])
        self.assertEqual(jobs([-50, -50, 50], 2, 2), [[0, 2], [1, 2], [2, 0], [2, 0]])
        self.assertEqual(jobs([0, 50, -50], 1, 2), [[0, 1], [1, 1]])
        self.assertEqual(jobs([0, 0, 0], 0, 0), [[0, 0]] * 4)

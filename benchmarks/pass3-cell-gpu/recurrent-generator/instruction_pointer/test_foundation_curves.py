import unittest
from types import SimpleNamespace

import torch
from torch import nn

from foundation_egg_catalogue import install
from foundation_fit import WideRead
from foundation_world import source


class FoundationTests(unittest.TestCase):
    def test_expanded_gru_starts_from_original_function_without_jitter(self):
        torch.manual_seed(71)
        g = nn.GRUCell(32, 32)
        for size in (1, 3):
            x = torch.randn(size, 32)
            h = torch.randn(size, 32)
            for width in (32, 128):
                expanded = WideRead(g, width, jitter=0.0)
                torch.testing.assert_close(expanded(x, h), g(x, h))
                torch.testing.assert_close(expanded(x[0], h[0]), g(x[0], h[0]))
                expanded(x, h).sum().backward()
                self.assertTrue(
                    all(
                        p.grad is not None and torch.all(p.grad.norm(dim=-1) > 0)
                        for p in expanded.parameters()
                    )
                )

    def test_extra_role_does_not_change_inputs_or_successor_rules(self):
        a = source(4, 5, 1, 351)
        b = source(4, 5, 2, 351)
        self.assertEqual(
            a.replace("((Seed x y)) ((Mid", "((Seed x y) (Permit x)) ((Mid"), b
        )

    def test_egg_catalogues_share_roots_and_require_internal_suffix(self):
        closed = [(0, 0, [(-1, 0)])] + [(i, i, [(i - 1, 3)]) for i in range(1, 5)]
        external = closed[:3] + [(3, 3, [(-1, 0)])] + closed[4:]
        for cat, lengths in (
            ("primitive", []),
            ("short", [2]),
            ("medium", [5]),
            ("multi", [2, 5]),
        ):
            world = SimpleNamespace(
                outputs=[{"result": 3}] * 5, layouts=[], export_pc={}
            )
            install(world, {0: closed, 1: external}, cat)
            self.assertEqual([len(layout) for layout in world.layouts], lengths)
            self.assertEqual(list(world.export_pc.values()), [3] * len(lengths))

import unittest
from types import SimpleNamespace

import torch

from actor import InstructionActor
from value_read_model import ValueRead, lane_products
from value_read_world import CUBES, SCHEMAS, field_pair, program


class TestReadout(unittest.TestCase):
    def test_batch_matches_full_token_ce_and_read_gradients(self):
        for v in "ABC":
            torch.manual_seed(18)
            model = ValueRead.__new__(ValueRead)
            torch.nn.Module.__init__(model)
            model.actor = InstructionActor()
            model.variant = v
            model.arm = "C"
            model.read_ports_at_template = True
            codes = torch.randn(2, 32)
            model.cache = torch.randn(3, 32), codes, torch.randn(1, 32)
            w = SimpleNamespace(
                layouts=[[(0, 0, [(-1, 0)])], [(1, 0, [(-1, 0)])]],
                cat=SimpleNamespace(
                    inputs={("generated", 0): [1], ("generated", 1): [2]}
                ),
            )
            words = (712, 712, 109, 6)
            ref = (-13, 0, 0)
            s = {
                "run": 2,
                "epoch": 2,
                "response": (1, 2, 0),
                "menu": [0, 1],
                "ports": [(ref, -13, -1, 0, words, False, ())],
            }
            m = model.state(w, s)
            ce = model.token_loss(w, m, (0, (ref,)))
            pars = [
                model.actor.query.weight,
                model.actor.next_read.weight_ih,
                model.actor.next_read.weight_hh,
                model.actor.input_role.weight,
            ]
            actual = torch.autograd.grad(ce, pars, retain_graph=True)
            lanes, role = lane_products([words])
            batch = model.singleton(
                codes, m["vals"], model.actor.latent(m["ext"]), lanes, role
            )
            torch.testing.assert_close(-batch[0, 0], ce)
            for x, y in zip(
                actual, torch.autograd.grad(-batch[0, 0], pars), strict=True
            ):
                torch.testing.assert_close(x, y, atol=2e-6, rtol=2e-5)

    def test_interface_has_no_cross_owner_access(self):
        lanes, role = lane_products([(1, 2, 3), (14, 14)])
        other, _ = lane_products([(21, 22, 23), (14, 14)])
        torch.testing.assert_close(lanes[1], other[1])
        torch.testing.assert_close(lanes[1, 1:], torch.zeros_like(lanes[1, 1:]))
        self.assertFalse(torch.equal(role[0], role[1]))

    def test_balanced_factors(self):
        for schema in SCHEMAS:
            i, k = field_pair(schema[0])
            strings = [
                program(schema, 999, b).split("(Seed ")[-1].splitlines()[0]
                for b in CUBES
            ]
            self.assertEqual(len(set(strings)), 8)
            for j in range(3):
                for bit in (0, 1):
                    labels = [(b[i] == b[k]) for b in CUBES if b[j] == bit]
                    self.assertEqual(sum(labels), 2)


if __name__ == "__main__":
    unittest.main()

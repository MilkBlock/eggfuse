import unittest
from types import SimpleNamespace
from unittest.mock import patch

import torch

from actor import InstructionActor
from operand_read_model import OperandRead, repeated_argument, words


class TestOperandRead(unittest.TestCase):
    def test_complete_ce_and_gradients_agree_with_free_decoder_path(self):
        for arm in "BCD":
            torch.manual_seed(97)
            model = OperandRead.__new__(OperandRead)
            torch.nn.Module.__init__(model)
            model.reader, model.variant, model.arm = arm, "C", "C"
            model.actor = InstructionActor()
            model.entry_menu = [0, 1]
            model.audit = False
            model.read_ports_at_template = True
            model.descriptors = torch.randn(2, 2, 32)
            nodes, codes, types = (
                torch.randn(5, 32),
                torch.randn(2, 32),
                torch.randn(1, 32),
            )
            model.cache = (nodes, codes, types)
            w = SimpleNamespace(
                layouts=[[(t, 0, [(-1, 0)])] for t in range(2)],
                cat=SimpleNamespace(inputs={("generated", t): [t] for t in range(2)}),
            )
            ref = (-17, 0, 0)
            hashes = (22, 31, 22, 19)
            state = {
                "run": 1,
                "epoch": 1,
                "response": (0, 0, 0),
                "menu": [0, 1],
                "ports": [(ref, -17, -1, 0, hashes, False, ())],
            }
            m = model.state(w, state)
            ce = model.token_loss(w, m, (1, (ref,)))
            fields, roles = words([hashes])
            batch = model.singleton(
                codes, m["vals"], model.actor.latent(m["ext"]), fields, roles
            )
            torch.testing.assert_close(ce, -batch[0, 1])
            params = (
                model.actor.query.weight,
                model.actor.lanes.weight,
                model.actor.input_role.weight,
            )
            expected = torch.autograd.grad(ce, params, retain_graph=True)
            for a, b in zip(
                expected, torch.autograd.grad(-batch[0, 1], params), strict=True
            ):
                torch.testing.assert_close(a, b, atol=1e-5, rtol=2e-5)

    def test_linear_reader_with_ragged_ports(self):
        torch.manual_seed(7)
        net = OperandRead.__new__(OperandRead)
        torch.nn.Module.__init__(net)
        net.actor = InstructionActor()
        net.reader = "D"
        net.descriptors = torch.randn(2, 2, 32)
        net.menu = [0, 1]
        net.audit = True
        q = torch.randn(2, 32)
        short = (0, 0, 0, 0, (11, 42))
        long = (0, 0, 0, 0, (9, 2, 3, 4, 5, 6))
        with patch.object(
            torch, "triu_indices", side_effect=AssertionError("constructed pairs")
        ):
            alone = net.read_interface(q, [short])
            mixed = net.read_interface(q, [long, short])
        torch.testing.assert_close(alone[:, 0], mixed[:, 1])
        weights, _ = net.trace
        self.assertEqual(weights.shape, (2, 2, 2, 6))
        self.assertTrue((weights[1, :, :, 2:] == 0).all())
        torch.testing.assert_close(weights.sum(-1), torch.ones(2, 2, 2))

    def test_static_repeated_slot(self):
        self.assertEqual(repeated_argument([{"slot": 0}, {"slot": 1}, {"slot": 0}]), 2)
        self.assertIsNone(repeated_argument([{"literal": 1}, {"literal": 1}]))


if __name__ == "__main__":
    unittest.main()

import unittest

import torch

from prefix_recovery import RecurrentRecoveryHead


class RefinementTest(unittest.TestCase):
    def test_extra_passes_reuse_weights_and_each_candidate_retains_its_identity(self):
        torch.manual_seed(123)
        one = RecurrentRecoveryHead(7, 1)
        three = RecurrentRecoveryHead(7, 3)
        three.load_state_dict(one.state_dict())
        context, port, evidence = torch.randn(4, 14), torch.randn(4, 7), torch.randn(4, 8)
        activations = []
        hook = three.refine.register_forward_hook(lambda *args: activations.append(1))
        scores = three(context, port, evidence)
        hook.remove()
        self.assertEqual(len(activations), 3)
        self.assertFalse(torch.allclose(scores, one(context, port, evidence)))
        torch.testing.assert_close(three(context.flip(0), port.flip(0), evidence.flip(0)), scores.flip(0))
        scores.sum().backward()
        self.assertGreater(three.refine.weight.grad.abs().sum().item(), 0)


if __name__ == '__main__':
    unittest.main()

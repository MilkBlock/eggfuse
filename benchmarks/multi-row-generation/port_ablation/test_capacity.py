import unittest

import torch
import torch.nn.functional as F

from capacity import WideSharedPointerHead
from decoder import PointerHead


class CapacityControl(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(1703)
        self.dim = 9
        self.rules = 5
        self.base = PointerHead(self.dim).double()
        self.queries = torch.randn(7, self.dim, dtype=torch.float64)
        self.inputs = torch.randn(7, 4, self.dim, dtype=torch.float64)

    def test_count_initial_equivalence_and_rng_isolation(self):
        state = torch.get_rng_state()
        wide = WideSharedPointerHead(self.base, self.rules, seed=17)
        torch.testing.assert_close(torch.get_rng_state(), state, rtol=0, atol=0)
        parameters = lambda model: sum(p.numel() for p in model.parameters())
        self.assertEqual(parameters(wide), self.rules * parameters(self.base))
        self.assertEqual(wide.key.weight.shape, (self.rules*self.dim, self.dim))
        base_scores = self.base.score(self.queries, self.base.key(self.inputs))
        wide_scores = wide.score(self.queries, wide.key(self.inputs))
        torch.testing.assert_close(wide_scores, base_scores, rtol=1e-12, atol=1e-12)

    def test_extra_key_then_extra_query_receive_gradients(self):
        wide = WideSharedPointerHead(self.base, self.rules, seed=1709)
        optimizer = torch.optim.SGD(wide.parameters(), lr=0.1)
        target = torch.arange(len(self.queries)) % self.inputs.shape[1]
        loss = F.cross_entropy(wide.score(self.queries, wide.key(self.inputs)), target)
        loss.backward()
        self.assertGreater(float(wide.key.weight.grad[self.dim:].abs().sum()), 0)
        self.assertEqual(float(wide.query.weight.grad[self.dim:].abs().sum()), 0)
        optimizer.step()
        optimizer.zero_grad()
        loss = F.cross_entropy(wide.score(self.queries, wide.key(self.inputs)), target)
        loss.backward()
        self.assertGreater(float(wide.query.weight.grad[self.dim:].abs().sum()), 0)
        query_part = wide.query(self.queries)[:, self.dim:]
        key_part = wide.key(self.inputs)[:, :, self.dim:]
        extra_score = torch.bmm(query_part.unsqueeze(1), key_part.transpose(1, 2))
        self.assertGreater(float(extra_score.detach().abs().max()), 0)


if __name__ == '__main__':
    torch.set_num_threads(1)
    unittest.main()

import unittest
import torch
from torch import nn
import numpy as np
from joint_partner import Partner, signs, align
from joint_partner_challenge import validate
from joint_partner_worlds import world


class JointKernel(unittest.TestCase):
    def tiny(self):
        net = Partner.__new__(Partner)
        nn.Module.__init__(net)
        net.arm = "tensor"
        net.bits = 7
        net.register_buffer("coords", torch.arange(28).reshape(4, 7))
        net.factors = nn.ParameterDict(
            {
                str(k): nn.Parameter(signs(k).expand(4, -1, -1).clone() * 2)
                for k in (2, 3, 4)
            }
        )
        return net

    def test_row_outer_product_and_positive_kernel(self):
        net = self.tiny()
        gen = torch.Generator().manual_seed(591)
        x = torch.randn(2, 6, 3, 64, generator=gen)
        z = net.phi(x)
        self.assertEqual(z.shape, (2, 6, 4, 128))
        torch.testing.assert_close(z.sum(-1), torch.ones(2, 6, 4))
        expected = 1
        off = 0
        for j, k in enumerate([3, 2, 2]):
            v = x[:, :, j, net.coords[:, off : off + k]]
            fe = torch.einsum("bnhc,hck->bnhk", v, net.factors[str(k)]).softmax(-1)
            expected = expected * (fe[:, 0] * fe[:, 1]).sum(-1)
            off += k
        torch.testing.assert_close(expected, (z[:, 0] * z[:, 1]).sum(-1))
        torch.testing.assert_close(
            net.evidence(z, z.sum(1)), torch.einsum("bnhk,bhk->bnh", z, z.sum(1))
        )
        torch.testing.assert_close(z[:, 3:].sum(1) + z[:, :3].sum(1), z.sum(1))

    def test_alignment_and_pairwise_marginals(self):
        raw = torch.arange(24).view(1, 2, 3, 4)
        torch.testing.assert_close(
            align(raw, torch.tensor([[2, 0]])), raw[:, :, [2, 0]]
        )

        def facts(n, flip, table):
            lines = world(170531, n, "three", flip, True, parity=True).splitlines()
            return np.array(
                [
                    list(map(int, s[1:-1].split()[1:]))
                    for s in lines
                    if s.startswith("(" + table + " ")
                ]
            )

        for n in (4, 8, 32):
            validate(facts(n, 0, "Mid"), facts(n, 1, "Mid"))
            self.assertTrue(np.array_equal(facts(n, 0, "Left"), facts(n, 1, "Left")))
            self.assertTrue(
                set(map(tuple, facts(4, 0, "Mid")))
                <= set(map(tuple, facts(n, 0, "Mid")))
            )

    def test_dense_limit(self):
        net = self.tiny()
        net.arm = "dense"
        x = torch.zeros(1, 33, 32)
        f = torch.zeros(1, 33, 4, 64)
        idx = torch.zeros(1, dtype=torch.long)
        inp = (
            torch.zeros(1, 32),
            torch.zeros(1, 2, 32),
            torch.zeros(1, 2, 2, 4, 4),
            [(x, f, idx), (x, f, idx)],
        )
        with self.assertRaisesRegex(ValueError, "offline"):
            net.messages(inp, [torch.zeros(1, 1, 2, dtype=torch.long)])


if __name__ == "__main__":
    unittest.main()

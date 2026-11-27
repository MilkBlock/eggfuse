import unittest
from unittest.mock import patch
import torch
from torch import nn
from first_parent import FirstParent


class EnergyFixture(FirstParent):
    def __init__(self, arm, left, right):
        nn.Module.__init__(self)
        self.arm = arm
        self.left = left
        self.energy = (
            torch.arange(left * right, dtype=torch.float).reshape(left, right) / 7
        )
        self.seen = []

    def root_prior(self, inputs):
        return torch.arange(self.left, dtype=torch.float).log_softmax(0)[None]

    def relation(self, inputs, ids):
        self.seen.append(ids.shape[1])
        return self.energy[ids]

    def pool_scores(self, inputs):
        return torch.zeros(1, self.left)


class FirstParentTest(unittest.TestCase):
    def test_both_conditionals_of_joint(self):
        net = EnergyFixture("joint", 4, 3)
        inputs = (None, None, None, [(torch.zeros(1, 4, 1),), (torch.zeros(1, 3, 1),)])
        y = torch.tensor([[[0, 0], [3, 2], [1, 2]]])
        (root, next_parent), _ = net(inputs, y)
        probs = (
            (net.root_prior(inputs)[0, :, None] + net.energy)
            .flatten()
            .softmax(0)
            .view_as(net.energy)
        )
        got = (
            root.gather(-1, y[:, :, 0, None]) + next_parent.gather(-1, y[:, :, 1, None])
        ).exp()
        torch.testing.assert_close(got[0, :, 0], probs[y[0, :, 0], y[0, :, 1]])
        torch.testing.assert_close(root[0, 0].exp(), probs.sum(1))
        # Row normalization erases completion mass exactly.
        torch.testing.assert_close(
            net.energy.log_softmax(1).logsumexp(1), torch.zeros(4)
        )

    def test_dense_limit_and_online_relation_width(self):
        inputs = (
            None,
            None,
            None,
            [(torch.zeros(1, 64, 1),), (torch.zeros(1, 47, 1),)],
        )
        noise = torch.tensor([[[0.2, 0.3], [0.4, 0.5]]])
        with self.assertRaises(ValueError):
            EnergyFixture("joint", 64, 47)(inputs, draws=2, noise=noise)
        net = EnergyFixture("pool", 64, 47)
        net(inputs, draws=2, noise=noise)
        self.assertEqual(net.seen, [2])

    def test_pool_block_permutation(self):
        net = EnergyFixture("pool", 4, 8)
        net.coordinates = torch.arange(28).reshape(4, 7)
        net.prototypes = nn.Parameter(torch.randn(4, 7, 128))
        net.strength = nn.Parameter(torch.tensor(1.0))
        left = torch.randn(1, 4, 3, 64)
        right = torch.randn(1, 8, 3, 64)

        def go(x, y):
            return FirstParent.pool_scores(
                net, (None, None, None, [(None, x), (None, y)])
            )

        with patch.object(net, "role_attention", return_value=torch.eye(3)[None] / 3):
            rev = [3, 1, 2, 0]
            torch.testing.assert_close(
                go(left[:, rev], right.flip([1])), go(left, right)[:, rev]
            )


if __name__ == "__main__":
    unittest.main()

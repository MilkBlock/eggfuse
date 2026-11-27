import unittest

import torch

from head_joint_index import Edge, PostingIndex
from partner_index import EXPLORE


class HeadIndexTest(unittest.TestCase):
    def test_marginal_and_width(self):
        for device in ["cpu"] + (["mps"] if torch.backends.mps.is_available() else []):
            # Two rows collide in all four feature heads, two share only some heads.
            base = torch.tensor(
                [
                    [262144, 262144, 1, 262144],
                    [131072, 131072, 3, 131072],
                    [180000, 180000, 180000, 39],
                    [13, 13, 13, 1],
                ],
                device=device,
            )
            ids = torch.stack((base, base + 1), -1)[None].int()
            frac = torch.tensor([0.25, 0.33, 0.6, 0.78], device=device)[
                None, None, :
            ].expand(1, 4, 4)
            v = torch.stack((1 - frac, frac), -1)
            weight = torch.tensor([[1.0, 3.0, 0.0, 0.5]], device=device)
            index = PostingIndex.build((ids, v), weight)
            # Query also contains an absent high half with its insertion point inside dictionary.
            qi = ids.clone()
            qi[:, :, 3, :] -= 1
            start, count, m = index.lookup((qi, v))
            k = (
                (
                    (qi[:, :, :, None, :, None] == ids[:, :, None, :, None, :])
                    * v[:, :, :, None, :, None]
                    * v[:, :, None, :, None, :]
                ).sum((-1, -2))
            ).prod(1) * weight[:, None]
            torch.testing.assert_close(m.sum(-1), k.sum(-1), atol=2e-6, rtol=1e-5)
            rng = torch.Generator().manual_seed(237)
            u = torch.rand((1, 30000, 4), generator=rng).to(device)
            root = torch.zeros((1, 30000), dtype=torch.long, device=device)
            got = (
                Edge(index, start, count, m)
                .draw(root, u)
                .cpu()
                .flatten()
                .bincount(minlength=4)
                / 30000
            )
            target = k[0, 0] / k[0, 0].sum() * (1 - EXPLORE) + EXPLORE / 4
            torch.testing.assert_close(got, target.cpu(), atol=0.012, rtol=0)

    def test_split_heads_and_reordered_publication(self):
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        # A partner per head with an agreeing coordinate. Only batch 1
        # has one partner supporting all four. The last row's identity moves.
        h = torch.arange(4, device=device)[:, None]
        b = torch.arange(4, device=device)[None, :]
        lo = torch.where(h == b, 262144, 131071)
        lo = torch.stack((lo, lo.clone()))
        lo[1, :, 2] = 262144
        ids = torch.stack((lo, lo + 1), -1).int()
        v = torch.zeros_like(ids, dtype=torch.float32)
        v[..., 0] = 1
        query = torch.full_like(ids[:, :, :1], 262144)
        query[..., 1] += 1
        root = torch.zeros((2, 1024), device=device, dtype=torch.long)
        u = torch.rand((2, 1024, 4), generator=torch.Generator().manual_seed(924)).to(
            device
        )
        u[..., 3] = 0.75
        for perm in ([0, 1, 2, 3], [2, 3, 0, 1]):
            idx = PostingIndex.build(
                (ids[:, :, perm], v[:, :, perm]), torch.ones((2, 4), device=device)
            )
            start, count, mass = idx.lookup((query, v[:, :, :1]))
            torch.testing.assert_close(mass.sum(-1).cpu(), torch.tensor([[0.0], [1.0]]))
            drawn = Edge(idx, start, count, mass).draw(root, u)
            self.assertEqual(drawn[0].unique().numel(), 4)
            self.assertTrue(bool((drawn[1] == perm.index(2)).all()))

import unittest
import torch
from selective_kernel import SparseMap, build_index, read_index


class SparseEvidence(unittest.TestCase):
    def test_pool_matches_dense_soft_basis_with_reference_weights(self):
        rng = torch.Generator().manual_seed(761)
        fields = (torch.rand((2, 9, 2, 64), generator=rng) > 0.5).float() * 2 - 1
        m = SparseMap()
        m.resolution = 16
        for variant in ("field-sparse", "joint-sparse", "mixed-sparse"):
            li, lv = m(fields[:, :4], variant)
            ri, rv = m(fields[:, 2:], variant)
            w = torch.rand((2, 7), generator=rng, requires_grad=True)
            out = read_index((li, lv), build_index((ri, rv), w))
            brute = (li[:, :, :, None, :, None] == ri[:, :, None, :, None, :]).float()
            brute = (
                (
                    brute
                    * lv[:, :, :, None, :, None]
                    * rv[:, :, None, :, None, :]
                    * w[:, None, None, :, None, None]
                )
                .sum((3, 4, 5))
                .transpose(1, 2)
            )
            torch.testing.assert_close(out, brute)
            torch.testing.assert_close(
                torch.autograd.grad(out.sum(), w, retain_graph=True)[0],
                torch.autograd.grad(brute.sum(), w, retain_graph=True)[0],
            )
            torch.testing.assert_close(
                torch.autograd.grad(out.sum(), m.logits, retain_graph=True)[0],
                torch.autograd.grad(brute.sum(), m.logits)[0],
                rtol=1e-4,
                atol=1e-4,
            )

    def test_reordering_and_segmented_updates(self):
        x = torch.arange(6, dtype=torch.float32).reshape(1, 1, 6, 1)
        ids = torch.cat([x // 2, x // 2 + 1], -1).int()
        v = torch.ones_like(ids, dtype=torch.float32) / 2
        w = torch.tensor([[1.0, 2.0, 3.0, 4.0, 2.0, 1.0]])
        q = (ids, v)
        result = read_index(q, build_index(q, w))
        parts = [
            read_index(q, build_index((ids[:, :, s], v[:, :, s]), w[:, s]))
            for s in (slice(0, 2), slice(2, None))
        ]
        torch.testing.assert_close(sum(parts), result)
        perm = torch.tensor([4, 3, 0, 2, 5, 1])
        torch.testing.assert_close(
            read_index(q, build_index((ids[:, :, perm], v[:, :, perm]), w[:, perm])),
            result,
        )

    def test_soft_collision_is_not_semantic_identity(self):
        h = SparseMap()
        h.resolution = 2
        x = torch.ones(1, 2, 2, 64)
        x[:, 1, 0, 0] = -1
        q = h(x, "mixed-sparse")
        prob = read_index(
            (q[0][:, :, :1], q[1][:, :, :1]),
            build_index((q[0][:, :, 1:], q[1][:, :, 1:]), torch.ones(1, 1)),
        )
        self.assertTrue((prob > 0).any())

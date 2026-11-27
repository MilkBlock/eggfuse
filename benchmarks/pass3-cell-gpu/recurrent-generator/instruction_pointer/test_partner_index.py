import unittest
import torch
from selective_kernel import SparseMap, build_index, read_index
from partner_index import Edge, take, dense_kernel, proposals, conditional


class NamedKernelTest(unittest.TestCase):
    def setUp(self):
        g = torch.Generator().manual_seed(205)

        def code(n):
            lo = torch.randint(4, (2, 4, n), generator=g)
            t = torch.rand(lo.shape, generator=g)
            return torch.stack((lo, lo + 1), -1).int(), torch.stack((t, 1 - t), -1)

        self.q = code(3)
        self.v = code(11)
        self.w = torch.rand(2, 11, generator=g)
        self.index = build_index(self.v, self.w, named=True)
        self.root = torch.tensor([[1], [2]])
        self.edge = Edge(self.q, self.v, self.index)

    def test_shared_summary_and_weighted_marginal(self):
        expected = build_index(self.v, self.w)
        for x, y in zip(self.index[:2], expected):
            torch.testing.assert_close(x, y)
        s = read_index(take(self.q, self.root), expected).mean(-1)[:, 0]
        k = dense_kernel(self.edge, self.root) * self.w
        torch.testing.assert_close(s, k.sum(1))
        u = torch.rand(2, 1, 65536, 2, generator=torch.Generator().manual_seed(50))
        r, _ = proposals(take(self.q, self.root), self.index, u)
        for idx in range(2):
            counts = r[idx].flatten().bincount(minlength=11) / 65536
            torch.testing.assert_close(counts, k[idx] / s[idx], rtol=0, atol=0.006)

    def test_zero_mass_and_inverse_cdf_plateaus(self):
        v = (self.v[0] + 20, self.v[1])
        edge = Edge(self.q, v, build_index(v, self.w, named=True))
        u = torch.rand(2, 32, 9, 5)
        for arm in ("linear", "refined"):
            ix, _ = conditional(edge, self.root.expand(2, 32), u, arm)
            torch.testing.assert_close(ix, (u[:, :, 0, 4] * 11).long())
        # Only row 7 has mass, even with zero-weight records before/after it.
        code = (
            torch.zeros((2, 4, 11, 2), dtype=torch.int),
            torch.full((2, 4, 11, 2), 0.5),
        )
        q = tuple(x[:, :, :1] for x in code)
        w = torch.zeros(2, 11)
        w[:, 7] = 1
        u = torch.tensor([0.0, 0.5, 0.99999994]).view(1, 1, 3, 1).expand(2, 1, 3, 2)
        ids, _ = proposals(q, build_index(code, w, named=True), u)
        self.assertTrue(bool((ids == 7).all()))

    def test_identical_readout_with_a_single_partner_in_proposal_support(self):
        v = (torch.zeros(1, 4, 3, 2, dtype=torch.int), torch.full((1, 4, 3, 2), 0.5))
        q = tuple(t[:, :, :1] for t in v)
        idx = build_index(v, torch.tensor([[0.0, 1.0, 0.0]]), named=True)
        u = torch.rand(1, 64, 9, 5)
        u[..., 3] = 1  # disable uniform exploration only for this deterministic check
        refs, _ = conditional(
            Edge(q, v, idx),
            torch.zeros(1, 64, dtype=torch.long),
            u,
            "shared-score",
            torch.tensor(0.5),
        )
        self.assertTrue(bool((refs == 1).all()))

    def test_publication_batch_invariance(self):
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        x = torch.randint(0, 2, (1, 1024, 2, 64)).float().mul(2).sub(1).to(device)
        m = SparseMap().to(device)
        whole = m(x, "mixed-sparse", fixed_order=True)
        delta = m(x[:, -32:].contiguous(), "mixed-sparse", fixed_order=True)
        for all_rows, changed in zip(whole, delta):
            torch.testing.assert_close(all_rows[:, :, -32:], changed, rtol=0, atol=0)

    def test_held_row_ordinal_tracks_the_same_reference_after_permutation(self):
        perm = torch.tensor([7, 3, 1, 2, 0, 8, 6, 4, 10, 5, 9])
        v = tuple(t[:, :, perm] for t in self.v)
        idx = build_index(v, self.w[:, perm], named=True)
        torch.testing.assert_close(
            read_index(self.q, self.index[:2]), read_index(self.q, idx[:2])
        )
        # Every stored ordinal points to a row actually carrying its indexed bin.
        for b in range(2):
            for h in range(4):
                matches = v[0][b, h, idx[2][b, h].long()] == idx[0][b, h, :, None]
                self.assertTrue(bool(matches.any(-1).all()))


if __name__ == "__main__":
    unittest.main()

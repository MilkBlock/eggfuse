from collections import Counter
from types import SimpleNamespace
import unittest

import torch

from replacement_stream import ReplacementStream


class ReceiptSkipping(unittest.TestCase):
    def setUp(self):
        self.stream = ReplacementStream.__new__(ReplacementStream)
        self.stream.stats = Counter()
        self.stream.roles = [[(1, 0), (2, 0)], [(3, 0), (5, 0), (7, 0)]]
        self.stream.order = [1, 0]
        self.stream.rd = SimpleNamespace(
            store=SimpleNamespace(
                visible={
                    a: {"version": 12} for ports in self.stream.roles for a in ports
                }
            )
        )

    def test_role_order_and_retirement(self):
        stream = self.stream
        parents = ((7, 0, 12), (1, 0, 12))
        self.assertEqual(stream.covered_paths([parents]), {(0, 2)})
        stream.rd.store.visible[(7, 0)]["version"] += 1
        self.assertEqual(stream.covered_paths([parents]), set())
        self.assertEqual(stream.covered_paths([((8, 0, 12), (1, 0, 12))]), set())

    def test_sparse_receipt_preserves_collision_neighbor(self):
        stream = self.stream
        stream.exclusions = {(0, 2), (1, 1)}
        paths = torch.tensor([[0], [1]])
        results = list(
            stream.posting_batches(
                paths,
                1,
                torch.tensor([0, 2, 1]),
                torch.tensor([0, 0]),
                torch.tensor([0, 2]),
                torch.tensor([2, 4]),
                4,
                1,
            )
        )
        self.assertEqual(
            [(a.item(), b.item()) for a, b in results], [(0, 0), (1, 0), (1, 2)]
        )
        self.assertEqual(stream.stats["omitted_positions"], 1)

    def test_dense_skip_and_post_score_agree(self):
        stream = self.stream
        stream.exclusions = {(0, 0), (0, 2), (1, 2)}
        stream.links = [[], []]
        batches = stream.children(torch.tensor([[0], [1]]), 1, 1)
        left = [(i.item(), j.item()) for i, j in batches]
        product = torch.cartesian_prod(torch.arange(2), torch.arange(3))
        right = stream.remove_scored(product, stream.exclusions, stream.stats)
        self.assertEqual(left, list(map(tuple, right.tolist())))
        self.assertEqual(stream.stats["omitted_positions"], 3)
        self.assertEqual(stream.stats["suppressed_after_score"], 3)

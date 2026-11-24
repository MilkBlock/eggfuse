import unittest
from collections import Counter
from types import SimpleNamespace

import torch

from stream_guard import GuardStream, Study


class GuardStreamTests(unittest.TestCase):
    def test_bucket_cursor_preserves_pairs_and_rule_watermark(self):
        stream = GuardStream.__new__(GuardStream)
        stream.roles = [[(1, 0), (2, 0)], [(3, 0), (4, 1), (5, 0), (6, 1)]]
        stream.links = [[], [(0, 0, 0)]]
        # Truncated neural codes collide. Distinct fields with codes 2 and 18
        # must remain eligible without a host equality check.
        codes = {
            a: (None, None, [c])
            for a, c in zip(
                stream.roles[0] + stream.roles[1], [2, 18, 2, 18, 3, 2], strict=True
            )
        }
        stream.rd = SimpleNamespace(index=SimpleNamespace(rows=codes))
        stream.tables = [
            (torch.tensor([False, True]),),
            (torch.tensor([True, False, True, False]),),
        ]
        stream.stats = Counter()
        stream.semi = True
        paths = torch.tensor([[0], [1]])
        for delta, expected in (
            (False, [(0, 0), (0, 1), (0, 3), (1, 0), (1, 1), (1, 3)]),
            (True, [(0, 0), (1, 0), (1, 1), (1, 3)]),
        ):
            stream.study = Study(bits=4, symmetric=True, delta_buckets=delta)
            stream.postings = {}
            batches = list(stream.children(paths, 1, 2))
            self.assertEqual(
                [
                    (i, j)
                    for left, right in batches
                    for i, j in zip(left.tolist(), right.tolist(), strict=True)
                ],
                expected,
            )
            self.assertTrue(all(len(left) <= 2 for left, _ in batches))

    def test_receipts_credit_only_the_named_nonempty_tuple(self):
        s = Study(collect=True)
        s.pending = list(torch.arange(4))
        batch = [{"parents": p} for p in ([], [1], [2], [3], [4])]
        s.verdicts(
            batch,
            list(
                enumerate(("accepted", "duplicate", "guard", "accepted", "watermark"))
            ),
            None,
        )
        self.assertEqual([int(x) for x in s.data], [1, 2])
        self.assertEqual(s.labels, [False, True])
        self.assertEqual(s.pending, [])

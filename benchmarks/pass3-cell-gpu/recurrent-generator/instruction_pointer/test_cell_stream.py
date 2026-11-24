import unittest
from collections import Counter
from types import SimpleNamespace

import torch

from cell_stream import CellStream
from recursive_agent import WIDTH, Compose


class CellStreamTest(unittest.TestCase):
    def test_chunking_and_resume_keep_exact_tuple_pairs(self):
        torch.manual_seed(7)
        st = CellStream.__new__(CellStream)
        st.model = Compose().eval()
        st.stats = Counter()
        st.rule = 0
        st.wm = 1
        st.roles = [[(11, 0), (12, 1)], [(21, 2), (22, 3)], [(31, 5), (32, 1)]]
        st.semi = True
        st.prepared = True
        st.rd = SimpleNamespace(meta=lambda _: torch.zeros(4))
        st.tables = [
            (
                torch.tensor([False, True]),
                torch.randn(2, WIDTH),
                torch.randn(2, 1, WIDTH),
                torch.randn(2, 1, WIDTH),
                torch.randn(2, 9),
            )
            for _ in st.roles
        ]
        st.links = [[], [(0, 0, 0)], [(1, 0, 0)]]

        def read(mode, threshold, block):
            it = st.batches(mode, threshold, float("inf"), block)
            first = next(it, [])
            rest = [p for batch in it for p in batch]
            self.assertEqual(len(first + rest), len(set(first + rest)))
            return set(first + rest)

        dense = read("dense", -100, 2)
        self.assertEqual(len(dense), 7)
        self.assertNotIn(tuple(v[0] for v in st.roles), dense)
        for threshold in (-100.0, 0.0, 100.0):
            self.assertEqual(read("dense", threshold, 7), read("stream", threshold, 2))
            self.assertEqual(
                read("dense", threshold, 2),
                {
                    p
                    for p, ok in zip(sorted(dense), st.named(sorted(dense), threshold))
                    if ok
                },
            )


if __name__ == "__main__":
    unittest.main()

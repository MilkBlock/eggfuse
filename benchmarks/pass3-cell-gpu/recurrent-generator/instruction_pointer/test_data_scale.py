import unittest

import numpy as np
import torch

from data_scale_corpus import program
from data_scale_train import subset_indices
from resident_page import shader


class CorpusTests(unittest.TestCase):
    def test_program_diversity_is_in_wiring(self):
        signatures = {program(i)[1] for i in range(32)}
        self.assertEqual(len(signatures), 32)
        self.assertEqual(program(19), program(19))

    def test_nested_program_balanced_subsets(self):
        sizes = np.full(210, 5000)
        a, b, c = [
            subset_indices(sizes, sum(sizes), n) for n in (10_000, 100_000, 1_000_000)
        ]
        self.assertTrue(np.array_equal(b[: len(a)], a))
        self.assertTrue(np.array_equal(c[: len(b)], b))
        self.assertEqual(len(set(a // 5000)), 16)
        self.assertEqual(len(set(b // 5000)), 64)


@unittest.skipUnless(torch.backends.mps.is_available(), "requires Metal")
class DeviceDraftTests(unittest.TestCase):
    @staticmethod
    def tensor(x):
        return torch.as_tensor(x, dtype=torch.int32, device="mps")

    def test_receipt_waits_for_publication_and_preserves_confirmed_version(self):
        lib = shader(136)
        ti = self.tensor
        # A consumer refers to local producer uid 7, op 0.
        draft = ti([[9, 0, -8, 0, 0]])
        roles = ti([0])
        meta = ti([[-1, 0, 0, 0, 0], [-1, -1, 1, 0, 0]])
        ident = ti([[0, 0, 0], [37, 0, 1]])
        pc = ti([1])

        def fix(uid):
            lib.fix_refs(
                draft,
                roles,
                meta,
                ident,
                pc,
                ti([1, 1, 1, 1, 1, 1, 1, 0, uid, 0, 136, 2]),
                threads=1,
            )
            return draft.cpu().tolist()[0][2:]

        self.assertEqual(fix(7), [1, 0, -1])
        self.assertEqual(fix(-1), [1, 0, -1])
        meta[1, :2] = ti([0, 4])
        self.assertEqual(fix(-1), [1, 0, 4])
        meta[1, 1] = 6
        self.assertEqual(fix(-1), [1, 0, 4])

    def test_deleting_producer_with_live_consumer_keeps_both(self):
        lib = shader(136)
        ti = self.tensor
        draft = ti([[1, 0, 0, 0, 0], [2, 2, -2, 0, 0]])
        ctl = ti([2, 3, 0, 1] + [0] * 13)
        emb = torch.zeros(2, 32, device="mps")
        lib.apply_jobs(
            draft,
            emb,
            ctl,
            ti([2, 1, 1, 1, 1, 1, 1, 0, 0, 0, 136, 4]),
            ti([[0, 1]]),
            draft,
            emb,
            ti([-1, 0]),
            ti([0, 0]),
            ti([0] * 4),
            threads=1,
        )
        self.assertEqual(ctl.cpu().tolist()[7], 1)
        self.assertEqual(ctl.cpu().tolist()[0], 2)

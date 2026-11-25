import unittest

import torch

from latent_cell_flow import WIDTH, Published


class ScalarEncoder:
    def ports(self, rows):
        return [torch.full((WIDTH,), float(r)) for r in rows]


class PublishedStateTest(unittest.TestCase):
    def test_overwrite_retire_and_preview_leave_pending_unconfirmed(self):
        state = Published(ScalarEncoder())
        a = dict(token=10, op=2)
        state.change(dict(retired=[], updates=[(a, 1)]), True)
        observed = state.total.clone()
        frame = dict(retired=[a], updates=[(a, 3), (a, 4)])
        preview = state.change(frame, False)
        torch.testing.assert_close(observed, state.total)
        self.assertEqual(state.live[10, 2][0], 1)
        torch.testing.assert_close(preview, state.change(frame, True))
        torch.testing.assert_close(state.total, torch.full_like(state.total, 4))
        self.assertEqual(state.live[10, 2][0], 4)
        state.change(dict(retired=[a], updates=[]), True)
        self.assertFalse(state.live)
        self.assertEqual(float(state.total.norm()), 0)

    def test_publishing_identical_row_is_idempotent(self):
        state = Published(ScalarEncoder())
        frame = dict(retired=[], updates=[(dict(token=0, op=1), 2)])
        state.change(frame, True)
        self.assertEqual(float(state.change(frame, True).norm()), 0)
        self.assertEqual(state.encodings, 2)


if __name__ == "__main__":
    unittest.main()

import unittest

import torch

from joint_slots import JointSlots


class JointSlotTests(unittest.TestCase):
    def test_candidate_permutation_preserves_complete_requests_and_stop(self):
        torch.manual_seed(122)
        head = JointSlots(8, 4)
        root = torch.randn(8)
        roles = torch.randn(2, 8)
        keys = [torch.randn(5, 8), torch.randn(3, 8)]
        fields = [torch.randn(len(k), 2, 64) for k in keys]
        fresh = [torch.rand(len(k)) for k in keys]
        wiring = [(0, 0, 1, 1), (1, 1, 0, 0)]
        logits, stop = head(root, roles, keys, fields, fresh, wiring, 2)
        perms = [torch.randperm(len(k)) for k in keys]
        def permute(tensors):
            return [t[p] for t, p in zip(tensors, perms, strict=True)]
        after, stop_after = head(root, roles, permute(keys), permute(fields), permute(fresh), wiring, 2)
        torch.testing.assert_close(stop_after, stop)
        for a,b,p in zip(logits, after, perms, strict=True):
            torch.testing.assert_close(a[:, p], b)
        sum(x.square().sum() for x in logits).backward()
        self.assertGreater(abs(head.field_weight.grad.item()), 0)

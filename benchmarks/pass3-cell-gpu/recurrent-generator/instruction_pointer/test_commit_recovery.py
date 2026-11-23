import unittest

import torch

from train_commit_recovery import set_loss


class CommitSetTests(unittest.TestCase):
    def test_multiple_proofs_earn_one_hit(self):
        probabilities = torch.tensor([[.3, .7, .9]])
        mask = torch.tensor([[True, True, False]])
        logits = probabilities.logit()
        want = -torch.tensor(1 - .7*.3).log() + .1*(.3+.7)
        observed = set_loss(logits,mask,torch.tensor([False]),.1)
        torch.testing.assert_close(observed,want)
        torch.testing.assert_close(observed,set_loss(logits.flip(1),mask.flip(1),torch.tensor([False]),.1))

    def test_same_proof_gets_different_credit_if_already_covered(self):
        for already_sent, sign in [(False,-1),(True,1)]:
            score = torch.zeros(1,1,requires_grad=True)
            set_loss(score,torch.tensor([[True]]),torch.tensor([already_sent]),.1).backward()
            self.assertGreater(sign*score.grad.item(),0)


if __name__ == '__main__':
    unittest.main()

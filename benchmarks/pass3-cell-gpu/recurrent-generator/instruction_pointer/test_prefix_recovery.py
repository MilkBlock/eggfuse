import unittest
from unittest.mock import patch
from collections import Counter
from types import SimpleNamespace

import torch

from prefix_policy import Policy
from prefix_recovery import select


class RecoveryBudgetTest(unittest.TestCase):
    def choose(self,scores,recovery,k,budget):
        scores=torch.tensor([scores])
        recovery=torch.tensor([recovery])
        prefix=torch.empty((1,0),dtype=torch.long)
        ids=torch.arange(scores.numel())
        head=SimpleNamespace(cut=0,budget=budget,scores=lambda *args:recovery)
        with patch('prefix_policy.score_tiles',return_value=[(prefix,ids,scores)]):
            result=select(SimpleNamespace(thresholds=[0,0,0]),None,None,None,0,0,[0],0,prefix,
                          Policy(k,recovery=head),Counter())
        return set(result.flatten().tolist())

    def test_original_choices_have_priority_and_tied_rescue_is_not_address_ordered(self):
        self.assertEqual(self.choose([1,-1,-2,-3],[0,2,1,1],3,2),{0,1})
        self.assertEqual(self.choose([1,1,-1],[0,0,9],1,1),set())
        self.assertEqual(self.choose([1,-1,-2,-3],[0,4,6,7],4,1),{0,3})


if __name__=='__main__':
    unittest.main()

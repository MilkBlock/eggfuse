import unittest
from types import SimpleNamespace

import torch

from binary_joint_audit import equally_many,top_pool
from sibling_issue import Allocation,SiblingHead,partitions,inputs,choose_second


class AllocationTests(unittest.TestCase):
    def test_equal_budget_without_address_tiebreak(self):
        scores=torch.tensor([5.,4.,4.,2.,1.,0.])
        first,base,rest=partitions(scores,4)
        self.assertEqual(first.tolist(),[0])
        self.assertCountEqual(base.tolist(),[1,2,3])
        head=SiblingHead(3)
        for p in head.parameters():p.data.zero_()
        x=[torch.zeros(6,d) for d in (9,3,3)]
        chosen,tied=choose_second(head,x,rest,base,True)
        self.assertTrue(tied)
        torch.testing.assert_close(chosen,base)

    def test_context_reads_named_columns_and_ignores_padding(self):
        mem=SimpleNamespace(keys=torch.randn(5,3),nodes=torch.randn(1,3),fields=torch.randn(5,4,64),
                            ports=[SimpleNamespace(hashes=(1,))]*5)
        cat=SimpleNamespace(roots={('generated',0):0})
        rows=torch.tensor([[1,0],[2,4],[3,1]])
        idx=torch.arange(3)
        x=inputs(cat,mem,0,rows,idx.float(),idx[:1])
        mem.fields[:,1:]=100.
        z=inputs(cat,mem,0,rows.flip(0),idx.float().flip(0),idx[-1:])
        for left,right in zip(x,z,strict=True):
            torch.testing.assert_close(left,right.flip(0))

    def test_joint_audit_discards_global_cutoff_ties_across_tiles(self):
        cols=torch.tensor([0,1])
        old=top_pool(None,torch.tensor([[4.,3.]]),torch.tensor([0]),cols,2)
        combined=top_pool(old,torch.tensor([[3.,1.]]),torch.tensor([1]),cols,2)
        left,right=equally_many(old,combined,2)
        self.assertEqual(left,[[0,0]])
        self.assertEqual(right,left)

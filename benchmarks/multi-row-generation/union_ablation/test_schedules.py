"""Controls for queued repeated unions, conditional repair, and false cache reuse."""
import unittest

import torch

from engine import kernels


class MetalSchedule(unittest.TestCase):
    def test_fixed_point_and_redundant_union(self):
        dev=torch.device('mps')
        # Reverse dependency order. Joining 0 and 1 implies 2=3 and then 4=5.
        words=torch.tensor([6,2,0,1,2,3,4,5,4,5,1,2,3,2,3,1,0,1],dtype=torch.int32,device=dev)
        classes=torch.arange(6,device=dev,dtype=torch.int32)[None,:]
        book=torch.zeros((1,23),device=dev,dtype=torch.int32)
        requests=torch.tensor([[4,5,2,3,0,1,0,5]],device=dev,dtype=torch.int32)
        def step(edges,flags):
            pairs=torch.tensor(edges,device=dev,dtype=torch.int32)
            snapshot=torch.empty((1,10),device=dev,dtype=torch.int32)
            kernels().advance(classes,book,pairs,requests,words,snapshot,flags,len(edges),
                              threads=1,arg_casts={6:'int32',7:'int32'})
            return snapshot[0,6:].tolist()
        self.assertEqual(step([[-1,-1]],2),[0,0,0,0])
        self.assertEqual(step([[0,1],[0,1]],3),[1,1,1,0])
        self.assertEqual(step([[1,0]],3),[1,1,1,0])
        # 3 incoming records, 2 flushes, 1 explicit merge/epoch, 2 derived edges.
        self.assertEqual(book[0,:4].tolist(),[3,2,1,1])
        self.assertEqual(book[0,6:9].tolist(),[2,4,3])
        self.assertEqual(book[0,12].item(),0)

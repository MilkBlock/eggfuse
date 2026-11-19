import unittest
import torch
from integral import device,Arena,device_plan


class MemberVisibility(unittest.TestCase):
    def test_absent_parent_and_stable_allocation(self):
        dev=device();name='rule-266';plan=device_plan(name,dev)
        # Four reflexive reads, one without a published physical parent.
        req=torch.zeros((1,4,5),dtype=torch.int32,device=dev)
        ports=torch.zeros((1,4,2),dtype=torch.int32,device=dev)
        bits=torch.zeros((1,2),dtype=torch.int32,device=dev)
        x=(None,None,req,None,ports,bits,bits,req[:,0],ports[:,0])
        inputs=torch.zeros((1,4,7),dtype=torch.int32,device=dev);inputs[0,1,0]=-1
        admit=torch.ones((1,4),dtype=torch.int32,device=dev)
        arena=Arena(x,plan)
        arena.step(0,x,inputs,admit,'integral')
        old=arena.snapshot();pages=[p.data_ptr() for p in arena.pages]
        for stage in (1,2):arena.step(stage,x,inputs,admit,'integral')
        self.assertEqual(arena.ref[0,4:8].tolist(),[-1]*4)
        self.assertEqual(arena.stats[0,:3].tolist(),[12]*3)
        self.assertEqual(arena.stats[0,12:16].tolist(),[0,3,3,3])
        self.assertEqual(old['pub'][0,:,0].ge(0).sum().item(),3)
        torch.testing.assert_close(old['ref'],arena.ref,atol=0,rtol=0)
        self.assertEqual(pages,[p.data_ptr() for p in arena.pages])

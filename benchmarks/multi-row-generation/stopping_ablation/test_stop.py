"""A quiet future seal, a pending congruence and a saved delta are three different obligations."""
import unittest
import torch
from queue_gpu import Queue,device,device_plan,restore,checkpoint,status


class StopContract(unittest.TestCase):
    def test_pending_and_two_step_repair_survive_suspension(self):
        dev=device();p=device_plan('rule-266',dev);local=p[2]
        events=torch.full((1,2,10),-1,device=dev,dtype=torch.int32)
        events[:,:,9]=0;events[0,0,:2]=local[0];events[0,0,2]=0
        events[0,1,9]=7
        addr=local[0].expand(1,4,2).contiguous()
        parent=torch.zeros((1,4,6),device=dev,dtype=torch.int32)
        args=(events,p[0],addr,parent)
        weights=torch.zeros(123,device=dev)
        q=Queue(1,p[3],dev);q.advance(args,weights,'exact',1,1)
        self.assertEqual(q.state[0,4:6].tolist(),[1,1])
        self.assertEqual(status(q.state).item(),1)
        cp=checkpoint(q,args);q.classes.fill_(-99)
        q,active=restore(cp);q.advance(active,weights,'exact',1,1)
        self.assertEqual(q.state[0,4:6].tolist(),[0,1])
        q.advance(active,weights,'exact',1,2)
        self.assertEqual(status(q.state).item(),2)
        self.assertEqual(q.visible[0,2].max().item(),-1)
        q.advance(active,weights,'exact',1,10)
        self.assertEqual(status(q.state).item(),4)
        self.assertEqual(q.state[0,21].item(),2)

    def test_permanent_wait_does_not_prove_closure(self):
        dev=device();p=device_plan('rule-266',dev)
        events=torch.full((1,2,10),-1,device=dev,dtype=torch.int32);events[:,:,9]=0
        req=p[2][0].expand(1,4,2).contiguous();parent=torch.zeros((1,4,6),device=dev,dtype=torch.int32)
        w=torch.zeros(123,device=dev);w[121]=1
        q=Queue(1,p[3],dev);q.advance((events,p[0],req,parent),w,'guard',1,16)
        self.assertEqual(q.state[0,21].item(),0)
        self.assertEqual(status(q.state).item(),3)

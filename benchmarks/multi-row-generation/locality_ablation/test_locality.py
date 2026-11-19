"""The same source handle on different owners is distinct until an edge connects it."""
import unittest

import torch

from network import Coordinator, certified_read


class LocalityContract(unittest.TestCase):
    def setUp(self):
        self.cert=torch.tensor([0,1])
        self.token=torch.zeros(1,3,56)
        self.token[0,:,33]=1
        self.token[0,:,50:55]=torch.tensor([[0,7,1,3,4],[1,7,5,6,4],[1,4,2,6,4]])
        self.token[0,:,-1]=torch.tensor([0,1,0])
        self.req=torch.tensor([[[0,7,1,7,2],[1,4,1,7,3]]])
        self.ports=torch.tensor([[[0,1],[0,1]]])
        self.phase=torch.ones(1,2,dtype=torch.int)
        self.receipts=self.phase.clone()
        self.edge=torch.tensor([[1,0,7,1,4]])
        self.ends=torch.tensor([[0,0]])

    def inputs(self):
        return self.req,self.ports,self.phase,self.receipts,self.edge,self.ends

    def test_cross_event_and_both_receipts(self):
        def active():
            return certified_read(self.token,self.inputs(),self.cert)['active'].tolist()[0]
        self.assertEqual(active(),[1,1])
        self.edge[0,0]=0
        self.assertEqual(active(),[0,1])
        self.edge[0,0]=1
        self.receipts[0,1]=0
        self.assertEqual(active(),[0,0])
        # A declared positive path still requires a live source Pair.
        self.receipts[0,1]=1
        self.token[0,1,32:34]=torch.tensor([1,0])
        self.assertEqual(active(),[0,0])

    def test_stale_reply_preserves_unrelated_state_and_can_resume(self):
        torch.manual_seed(7)
        policy=Coordinator()
        state=policy.prepare(self.token,self.inputs(),self.cert,'local')
        current,_,_,_=policy.finish(self.token,self.inputs(),self.cert,state)
        stale,_,pending,_=policy.finish(self.token,self.inputs(),self.cert,state,'stale')
        self.assertEqual(pending.tolist(),[[True,False]])
        self.assertFalse(stale['active'][0,0].item())
        self.assertTrue((stale['rows'][0,0]==-1).all().item())
        fresh,*_=policy.finish(self.token,self.inputs(),self.cert,state)
        for k in fresh:
            torch.testing.assert_close(current[k],fresh[k],atol=0,rtol=0)
            torch.testing.assert_close(current[k][:,1],stale[k][:,1],atol=0,rtol=0)


if __name__=='__main__':
    unittest.main()

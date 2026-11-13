import unittest
import numpy as np
from multi_entry_ridge import encode,scalar,pooling,replay,WIDTH,state_key,encoding_audit

class MultiEntryRidge(unittest.TestCase):
    def test_node_ids_not_float_features(self):
        roles=np.random.default_rng(1).normal(size=(3,64)).astype(np.float32)
        first=[(0,{},('E',10)),(1,{},('E',10)),(2,{},('E',20))]
        renamed=[(0,{},('E',900)),(1,{},('E',900)),(2,{},('E',5))]
        np.testing.assert_array_equal(encode(first,roles),encode(renamed,roles))
        distinct=[(0,{},('E',10)),(1,{},('E',30)),(2,{},('E',20))]
        self.assertGreater(np.max(abs(encode(first,roles)-encode(distinct,roles))),.01)

    def test_encoding_audit_catches_slot_information_loss(self):
        roles=np.zeros((2,64),np.float32)
        a=[(0,dict(sort='i64',value=2),None),(1,dict(sort='i64',value=3),None)]
        b=[(0,dict(sort='i64',value=3),None),(1,dict(sort='i64',value=2),None)]
        nodes=[dict(valid=True,target=encode(r,roles),state_key=state_key(r)) for r in (a,b)]
        self.assertEqual(encoding_audit(nodes)['conflicting_codes'],1)

    def test_dynamic_scalar_changes_code(self):
        self.assertFalse(np.array_equal(scalar(dict(sort='i64',value=2)),scalar(dict(sort='i64',value=3))))

    def test_all_providers_contribute(self):
        nodes=[dict(edges=[]),dict(edges=[]),dict(edges=[(0,np.ones(WIDTH)),(1,np.ones(WIDTH))])]
        states=np.array([np.ones(WIDTH),np.full(WIDTH,3),np.zeros(WIDTH)],np.float32)
        np.testing.assert_allclose(pooling(nodes,states)[2],4/np.sqrt(2),rtol=1e-6)

    def test_predicted_states_feed_later_layers(self):
        zero=np.zeros(WIDTH,np.float32)
        nodes=[dict(seed=zero,q=np.zeros(64),target=np.ones(WIDTH),edges=[],valid=True,depth=0),
               dict(seed=zero,q=np.zeros(64),target=np.ones(WIDTH),edges=[(0,np.ones(WIDTH))],valid=True,depth=1)]
        w=np.zeros((448,1),np.float32);coef=np.zeros((450,WIDTH),np.float32)
        coef[0]=.2
        for i in range(WIDTH):coef[1+WIDTH+64+i,i]=1
        out=replay(nodes,w,coef,False)
        np.testing.assert_allclose(out[0],np.tanh(.2),rtol=1e-6)
        np.testing.assert_allclose(out[1],np.tanh(.2+np.tanh(.2)),rtol=1e-6)

if __name__=='__main__':unittest.main()

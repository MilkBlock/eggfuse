import unittest
import numpy as np
from token_eq_readout import pair_layout,check_partition,features,static_equalities,materialize

class TokenEqReadout(unittest.TestCase):
    def test_pairs_are_typed_and_do_not_include_reflexive_labels(self):
        rule=dict(query=[],effects=[],slots=[dict(sort=dict(kind='eq',name='E')),
            dict(sort=dict(kind='eq',name='F')),dict(sort=dict(kind='eq',name='E')),
            dict(sort=dict(kind='i64',name='i64'))])
        pairs,*_=pair_layout(rule)
        self.assertEqual(pairs,[(0,2)])

    def test_false_merges_and_nontransitivity_are_reported(self):
        r=check_partition([(0,1),(0,2),(1,2)],np.array([True,False,False]),np.array([.9,.1,.9]))
        self.assertEqual(r['false_merges'],1);self.assertEqual(r['closure_false_merges'],2)
        self.assertTrue(r['nontransitive']);self.assertFalse(r['exact'])

    def test_no_queries_are_not_success(self):
        self.assertFalse(check_partition([],np.array([],bool),np.array([]))['exact'])

    def test_completed_copy_and_union_proofs_are_transitive(self):
        rule=dict(query=[],slots=[dict(sort=dict(kind='eq',name='E')) for _ in range(3)],
            effects=[dict(kind='copy',dst=1,arg=dict(slot=0)),dict(kind='union',args=[dict(slot=1),dict(slot=2)])])
        pairs,*_=pair_layout(rule)
        np.testing.assert_array_equal(static_equalities(rule,pairs),[True,True,True])
        rule['effects']=[]
        np.testing.assert_array_equal(static_equalities(rule,pairs),[False,False,False])

    def test_proved_pairs_are_not_sent_to_learned_decoder(self):
        r=dict(index=0,pairs=[(0,1),(0,2)],static=np.array([True,False]),y=np.array([True,False]),
            q=np.zeros(64),s=np.zeros((2,64)),d=np.zeros((2,64)),p=np.zeros((2,64)))
        x,y=materialize([r],np.zeros((1,128)),np.zeros((512,2)),True)
        self.assertEqual(x.shape,(1,515));np.testing.assert_array_equal(y,[False])

    def test_pair_features_are_symmetric_and_use_static_slots(self):
        rule=dict(query=[],effects=[],slots=[dict(sort=dict(kind='eq',name='E')) for _ in range(3)])
        pairs,q,s,d,p=pair_layout(rule)
        self.assertFalse(np.array_equal(s[0],s[1]))
        w=np.zeros((512,2),np.float32);z=np.zeros((len(pairs),128),np.float32)
        x=features(z,np.broadcast_to(q,(len(pairs),64)),s,d,p,w,np)
        self.assertEqual(x.shape,(3,515))

if __name__=='__main__':unittest.main()

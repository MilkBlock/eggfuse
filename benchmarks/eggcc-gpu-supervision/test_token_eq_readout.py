import unittest
import numpy as np
from token_eq_readout import pair_layout,check_partition,features,static_equalities,materialize,quotient_layout,readout_rows,expand_scores

class TokenEqReadout(unittest.TestCase):
    def test_port_interactions_preserve_original_columns_and_execute_on_gpu(self):
        import mlx.core as mx
        rng=np.random.default_rng(71)
        z=rng.normal(size=(5,128)).astype(np.float32)
        q,s,d,p=[rng.normal(size=(5,64)).astype(np.float32) for _ in range(4)]
        w=rng.normal(0,.01,(512,16)).astype(np.float32)
        wide=np.concatenate([w,np.zeros((256,16),np.float32)])
        original=features(z,q,s,d,p,w,np);extended=features(z,q,s,d,p,wide,np)
        np.testing.assert_array_equal(original[:,:513],extended[:,:513])
        np.testing.assert_allclose(original[:,513:],extended[:,769:],atol=2e-6)
        np.testing.assert_array_equal(extended[:,513:577],z[:,:64]*p)
        dw=mx.array(wide)
        out=mx.compile(lambda z,q,s,d,p:features(z,q,s,d,p,dw,mx))(*map(mx.array,(z,q,s,d,p)))
        mx.eval(out);np.testing.assert_allclose(np.array(out),extended,atol=2e-6)
        with self.assertRaises(ValueError):features(z,q,s,d,p,np.zeros((513,16)),np)

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

    def test_quotient_shares_queries_and_restores_every_original_pair(self):
        rule=dict(query=[],slots=[dict(sort=dict(kind='eq',name='E')) for _ in range(4)],
            effects=[dict(kind='copy',dst=1,arg=dict(slot=0)),dict(kind='copy',dst=3,arg=dict(slot=2))])
        pairs,q,s,d,p=pair_layout(rule);proof=static_equalities(rule,pairs)
        plan=quotient_layout(rule,pairs,proof)
        self.assertEqual(len(plan['representatives']),1)
        r=dict(index=0,pairs=pairs,q=q,s=s,d=d,p=p,static=proof,quotient=plan,y=proof.copy())
        query=readout_rows([r],True)[0]
        self.assertEqual(len(query['y']),1)
        np.testing.assert_array_equal(expand_scores(r,np.array([.1]),True,True)>=.5,proof)
        np.testing.assert_array_equal(expand_scores(r,np.array([.9]),True,True)>=.5,np.ones(6,bool))
        # A dynamic equality disagreement inside one class pair must not be hidden.
        r['y'][1]=True
        with self.assertRaisesRegex(ValueError,'inconsistent'):readout_rows([r],True)

    def test_quotient_keeps_sorts_separate_and_empty_queries_valid(self):
        rule=dict(query=[],slots=[dict(sort=dict(kind='eq',name=n)) for n in ['E','E','F','F']],
            effects=[dict(kind='union',args=[dict(slot=0),dict(slot=1)])])
        pairs,*_=pair_layout(rule);proof=static_equalities(rule,pairs);plan=quotient_layout(rule,pairs,proof)
        self.assertEqual(pairs,[(0,1),(2,3)])
        np.testing.assert_array_equal(plan['expansion'],[-1,0])
        rule['effects'].append(dict(kind='union',args=[dict(slot=2),dict(slot=3)]))
        plan=quotient_layout(rule,pairs,static_equalities(rule,pairs))
        self.assertEqual(plan['s'].shape,(0,64))
        np.testing.assert_array_equal(expand_scores(dict(quotient=plan),np.array([]),True,True),[1,1])

    def test_pair_features_are_symmetric_and_use_static_slots(self):
        rule=dict(query=[],effects=[],slots=[dict(sort=dict(kind='eq',name='E')) for _ in range(3)])
        pairs,q,s,d,p=pair_layout(rule)
        self.assertFalse(np.array_equal(s[0],s[1]))
        w=np.zeros((512,2),np.float32);z=np.zeros((len(pairs),128),np.float32)
        x=features(z,np.broadcast_to(q,(len(pairs),64)),s,d,p,w,np)
        self.assertEqual(x.shape,(3,515))

if __name__=='__main__':unittest.main()

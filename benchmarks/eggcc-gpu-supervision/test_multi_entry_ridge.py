import unittest
import numpy as np
from multi_entry_ridge import encode,scalar,pooling,replay,WIDTH,state_key,encoding_audit,input_seed

class MultiEntryRidge(unittest.TestCase):
    def test_source_context_keeps_baseline_projection_fixed(self):
        from multi_entry_ridge import projection
        base=projection(1408);extended=projection(1536,True)
        np.testing.assert_array_equal(base[:384],extended[:384])
        np.testing.assert_array_equal(base[384:],extended[512:])
        rng=np.random.default_rng(82);x=rng.normal(size=(3,1408)).astype(np.float32)
        more=np.concatenate([x[:,:384],np.zeros((3,128),np.float32),x[:,384:]],axis=1)
        np.testing.assert_allclose(x@base,more@extended,atol=2e-6)

    def test_source_context_uses_template_connections_not_future_results(self):
        from unittest.mock import patch
        from copy import deepcopy
        from multi_entry_ridge import dataset
        sort=dict(kind='eq',name='E')
        rule=dict(slots=[dict(sort=sort)],query=[dict(call=dict(name='F'),args=[dict(slot=0)])],effects=[])
        binding=dict(rule=0,values=[dict(slot=0,value={})],eq_ports=[dict(slot=0,sort='E',before=1)],
                     rhs=dict(completed=True,slots=[dict(slot=0,value={},eq_port=dict(sort='E',after_run=1))]))
        trace=dict(recipe=dict(rules=[rule]),runs=[dict(ordinal=i,audit=dict(bindings=[deepcopy(binding)])) for i in range(2)])
        links=dict(windows=[dict(consumer_run=1,producer_run=0,groups=[dict(providers=[dict(binding=0,rule=0,slot=0)])],
                                consumers=[dict(binding=0,ports=[dict(slot=0,group=0)])])])
        def make(t):
            with patch('historical_cell_sources.link_history',return_value=links):
                return dataset(t,4,False,'class-history-neighborhood-input',True)
        before=make(trace)
        self.assertEqual(before[1]['edge_interfaces'],[dict(input_slot=0,source_slot=0,source_rule=0,alternatives=1)])
        changed=deepcopy(trace);changed['runs'][1]['audit']['bindings'][0]['rhs']['slots'][0]['eq_port']['after_run']=99
        after=make(changed)
        np.testing.assert_array_equal(before[1]['q'],after[1]['q'])
        self.assertEqual(before[1]['edge_interfaces'],after[1]['edge_interfaces'])
        self.assertEqual(before[1]['q'].shape,(384,))
        np.testing.assert_array_equal(before[0]['q'][-128:],np.zeros(128))
        self.assertGreater(np.max(abs(before[1]['q'][-128:])),.01)

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

    def test_class_balancing_removes_duplicate_role_weight(self):
        rng=np.random.default_rng(91)
        roles=rng.normal(size=(3,64)).astype(np.float32);roles[1]=roles[0]
        one=[(0,{},('E',10)),(2,{},('E',20))]
        duplicate=[(0,{},('E',10)),(1,{},('E',10)),(2,{},('E',20))]
        np.testing.assert_allclose(encode(one,roles,'class-balanced'),encode(duplicate,roles,'class-balanced'),atol=1e-7)
        self.assertGreater(np.max(abs(encode(one,roles)-encode(duplicate,roles))),.01)
        distinct=[(0,{},('E',10)),(1,{},('E',30)),(2,{},('E',20))]
        self.assertGreater(np.max(abs(encode(duplicate,roles,'class-balanced')-encode(distinct,roles,'class-balanced'))),.01)
        np.testing.assert_array_equal(encode(duplicate,roles,'class-balanced'),encode(duplicate,roles,'class-interface'))
        renamed=[(0,{},('E',99)),(1,{},('E',99)),(2,{},('E',33))]
        np.testing.assert_array_equal(encode(duplicate,roles,'class-balanced'),encode(renamed,roles,'class-balanced'))

    def test_balanced_scalars_remain_individual_dynamic_values(self):
        roles=np.random.default_rng(92).normal(size=(2,64)).astype(np.float32)
        a=[(0,dict(sort='i64',value=2),None),(1,dict(sort='i64',value=3),None)]
        np.testing.assert_allclose(encode(a,roles),encode(a,roles,'class-balanced'),atol=1e-7,rtol=1e-6)
        b=[(0,dict(sort='i64',value=3),None),(1,dict(sort='i64',value=2),None)]
        self.assertFalse(np.array_equal(encode(a,roles,'class-balanced'),encode(b,roles,'class-balanced')))
        np.testing.assert_array_equal(encode([],roles,'class-balanced'),np.zeros(WIDTH))
        with self.assertRaises(ValueError):encode(a,roles,'unknown')

    def test_connected_interface_retains_known_equality_without_future_values(self):
        roles=np.random.default_rng(93).normal(size=(2,64)).astype(np.float32)
        def binding(second):
            return dict(values=[dict(slot=i,value={}) for i in (0,1)],
                eq_ports=[dict(slot=0,sort='E',before=10),dict(slot=1,sort='E',before=second)])
        a,b=binding(10),binding(20)
        np.testing.assert_array_equal(input_seed(a,roles,{0,1},'class-balanced'),input_seed(b,roles,{0,1},'class-balanced'))
        self.assertGreater(np.max(abs(input_seed(a,roles,{0,1},'class-interface')-input_seed(b,roles,{0,1},'class-interface'))),.01)
        # No RHS results or post-Run fields exist in these inputs.
        np.testing.assert_array_equal(input_seed(a,roles,set(),'class-balanced'),input_seed(a,roles,set(),'class-interface'))

    def test_dynamic_scalar_changes_code(self):
        self.assertFalse(np.array_equal(scalar(dict(sort='i64',value=2)),scalar(dict(sort='i64',value=3))))

    def test_all_providers_contribute(self):
        nodes=[dict(edges=[]),dict(edges=[]),dict(edges=[(0,np.ones(WIDTH)),(1,np.ones(WIDTH))])]
        states=np.array([np.ones(WIDTH),np.full(WIDTH,3),np.zeros(WIDTH)],np.float32)
        np.testing.assert_allclose(pooling(nodes,states)[2],4/np.sqrt(2),rtol=1e-6)

    def test_role_channels_distinguish_swapped_provider_connections(self):
        one=np.ones(WIDTH,np.float32)
        a=one;b=one
        nodes=[dict(edge_width=2*WIDTH,edges=[]),dict(edge_width=2*WIDTH,edges=[]),
               dict(edge_width=2*WIDTH,edges=[(0,a),(1,b)],edge_routes=[np.array([1,1]),np.array([1,-1])])]
        states=np.array([one,3*one,0*one])
        first=pooling(nodes,states)[2]
        nodes[2]['edges']=[(1,a),(0,b)]
        swapped=pooling(nodes,states)[2]
        np.testing.assert_array_equal(first[:WIDTH],swapped[:WIDTH])
        self.assertGreater(np.max(abs(first[WIDTH:]-swapped[WIDTH:])),1)

    def test_factored_channel_gemm_equals_expanded_edges(self):
        rng=np.random.default_rng(5);states=rng.normal(size=(3,WIDTH)).astype(np.float32)
        edges=[(0,rng.normal(size=WIDTH).astype(np.float32)),(1,rng.normal(size=WIDTH).astype(np.float32))]
        routes=rng.normal(size=(2,4)).astype(np.float32)
        nodes=[dict(edge_width=4*WIDTH,edges=[]),dict(edge_width=4*WIDTH,edges=[]),
               dict(edge_width=4*WIDTH,edges=edges,edge_routes=routes)]
        expected=sum((np.outer(r,states[i]*v).reshape(-1) for (i,v),r in zip(edges,routes)))/np.sqrt(2)
        np.testing.assert_allclose(pooling(nodes,states)[2],expected,atol=1e-6,rtol=1e-6)

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

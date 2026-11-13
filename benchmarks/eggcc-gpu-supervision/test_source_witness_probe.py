import unittest
from copy import deepcopy
import numpy as np
import mlx.core as mx
from source_witness_probe import choose,fixed_alpha_fit
from multi_entry_ridge import pooling,features


def fixture():
    empty=dict(edges=[],edge_interfaces=[],edge_routes=[],depth=0,edge_width=512)
    route=np.ones(4,np.float32);edge=np.ones(128,np.float32)
    node=dict(empty,edges=[(0,edge/np.sqrt(2)),(1,edge*2/np.sqrt(2)),(1,edge*3)],
        edge_routes=[route,route*.5,route*2],
        edge_interfaces=[dict(input_slot=0,source_slot=2,source_rule=7,alternatives=2),
            dict(input_slot=0,source_slot=5,source_rule=9,alternatives=2),
            dict(input_slot=1,source_slot=6,source_rule=9,alternatives=1)])
    return [dict(empty),dict(empty),node]


class WitnessTests(unittest.TestCase):
    def test_one_source_per_input_without_losing_shared_provider(self):
        nodes=fixture();first=choose(nodes,'first');last=choose(nodes,'last')
        self.assertEqual([i for i,_ in first[2]['edges']],[0,1])
        self.assertEqual([i for i,_ in last[2]['edges']],[1,1])
        np.testing.assert_allclose(first[2]['edges'][0][1],1,atol=1e-7)
        self.assertEqual([p['source_slot'] for p in last[2]['edge_interfaces']],[5,6])
        self.assertEqual(len(nodes[2]['edges']),3)
        self.assertTrue(first[2]['multiple']);self.assertFalse(last[2]['multiple'])
        self.assertEqual(last[2]['depth'],1)

    def test_selection_independent_of_labels_and_rejects_invalid_metadata(self):
        nodes=fixture();before=choose(nodes,'mixed')
        for n in nodes:n['target']=np.full(128,999)
        after=choose(nodes,'mixed')
        for a,b in zip(before[2]['edges'],after[2]['edges']):
            self.assertEqual(a[0],b[0]);np.testing.assert_array_equal(a[1],b[1])
        bad=deepcopy(nodes);bad[2]['edge_interfaces'][0]['alternatives']=3
        with self.assertRaises(ValueError):choose(bad,'first')
        bad=deepcopy(nodes);bad[2]['edges'][0]=(2,bad[2]['edges'][0][1])
        with self.assertRaises(ValueError):choose(bad,'first')

    def test_fixed_fit_never_normalizes_or_fits_using_validation(self):
        x=np.array([[1,0],[1,1],[1,2],[1,3]],np.float32)
        y=np.array([[0],[1],[2],[3]],np.float32)
        mask=np.array([True,True,True,False])
        a,report=fixed_alpha_fit(x,y,mask,~mask,1.)
        x[-1,1]=999;y[-1]=999
        b,_=fixed_alpha_fit(x,y,mask,~mask,1.)
        np.testing.assert_array_equal(a,b)
        self.assertTrue(report['fixed_alpha'])
        with self.assertRaises(ValueError):fixed_alpha_fit(x,y,mask,~mask,0.)

    def test_single_witness_feature_normalization_matches_live_gpu_inference(self):
        from test_device_ridge_transition import fixture as live_fixture
        from device_ridge_transition import infer
        state,request,model=live_fixture()
        state['tokens']=np.tanh(state['tokens'])
        state['present'][:]=True;state['visible'][:]=True;state['settled'][:]=True
        for policy in ('first','last'):
            nodes=choose(fixture(),policy);n=nodes[2]
            req={k:v[:1].copy() for k,v in request.items()}
            req.update(sources=np.array([[i for i,_ in n['edges']]],np.int32),
                edge=np.array([[v for _,v in n['edges']]],np.float32),
                route=np.array([n['edge_routes']],np.float32),edge_valid=np.ones((1,2),bool))
            pool=pooling(nodes,state['tokens'])[2:3]
            expected=np.tanh(features(req['seed'],req['q'],pool,model['w'],np)@model['coef'])
            dev=lambda d:{k:mx.array(v) for k,v in d.items()}
            ds,dr,dm=map(dev,(state,req,model))
            out,marks=mx.compile(lambda s,r:infer(s,r,dm,mx))(ds,dr);mx.eval(out,marks)
            self.assertTrue(np.array(marks['ready']).all())
            np.testing.assert_allclose(np.array(out),expected,atol=3e-6)

if __name__=='__main__':unittest.main()

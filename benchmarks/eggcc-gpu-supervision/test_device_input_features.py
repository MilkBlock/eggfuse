import unittest
import numpy as np
import mlx.core as mx
from device_input_features import compile_inputs,encode_inputs,infer_from_slots
from multi_entry_ridge import template,neighborhood_template,encode,scalar
from device_ridge_transition import infer


class InputFeatures(unittest.TestCase):
    def fixture(self):
        rule=dict(slots=[dict(sort=dict(kind='eq',name='E'),definition='query') for _ in range(2)]+[dict(sort=dict(kind='primitive',name='i64'),definition='query')],
            query=[dict(call=dict(table='F'),args=[dict(slot=0),dict(slot=2),dict(slot=1)])],effects=[])
        inp=dict(roots=np.array([[7,7,-1],[7,8,-1]],np.int32),valid=np.ones((2,3),bool),numeric=np.array([[False,False,True]]*2),
            numbers=np.array([[0,0,3],[0,0,-9]],np.float32),scalar_codes=np.zeros((2,3,64),np.float32),scalar_valid=np.zeros((2,3),bool))
        return rule,inp

    def test_gpu_numeric_and_neighbor_features_match_training(self):
        rule,inp=self.fixture();layout=compile_inputs(rule);roles,q=template(rule);near,nq=neighborhood_template(rule)
        seeds=[];queries=[]
        for i in range(2):
            rows=[(j,{},('E',int(inp['roots'][i,j]))) for j in range(2)]+[(2,dict(sort='i64',value=int(inp['numbers'][i,2])),None)]
            seeds.append(encode(rows,roles,'class-balanced'));queries.append(np.concatenate([q,encode(rows,near,'class-balanced'),nq]))
        out,m=encode_inputs(inp,layout,np)
        np.testing.assert_allclose(out['seed'],seeds,atol=2e-6);np.testing.assert_allclose(out['q'],queries,atol=2e-6)
        if mx.metal.is_available():
            dl={k:mx.array(v) for k,v in layout.items()};di={k:mx.array(v) for k,v in inp.items()}
            result,marks=mx.compile(lambda x:encode_inputs(x,dl,mx))(di);mx.eval(result,marks)
            np.testing.assert_allclose(np.array(result['seed']),seeds,atol=2e-6)
            np.testing.assert_allclose(np.array(result['q']),queries,atol=2e-6)

    def test_encode_and_ridge_execute_without_intermediate_host_features(self):
        if not mx.metal.is_available():self.skipTest('Metal required')
        rule,inp=self.fixture();layout=compile_inputs(rule)
        state=dict(tokens=np.zeros((2,128),np.float32),generation=np.ones(2,np.int32))
        for k in ('present','visible','settled'):state[k]=np.ones(2,bool)
        request=dict(sources=np.zeros((2,1),np.int32),generations=np.ones((2,1),np.int32),edge_valid=np.zeros((2,1),bool),
                     edge=np.zeros((2,1,128),np.float32),route=np.zeros((2,1,4),np.float32))
        rng=np.random.default_rng(11);model=dict(w=rng.normal(0,.01,(1408,16)).astype(np.float32),coef=rng.normal(0,.01,(1425,128)).astype(np.float32))
        expected,_,_=infer_from_slots(state,request,model,inp,layout,np)
        dev=lambda x:{k:mx.array(v) for k,v in x.items()}
        ds,dr,dm,di,dl=map(dev,(state,request,model,inp,layout))
        out,marks,encoded=mx.compile(lambda x:infer_from_slots(ds,dr,dm,x,dl,mx))(di);mx.eval(out,marks,encoded)
        np.testing.assert_allclose(np.array(out),expected,atol=2e-6)
        self.assertTrue(np.array(marks['ready']).all())
        self.assertGreater(float(np.max(np.abs(expected[0]-expected[1]))),1e-4)

    def test_missing_numeric_or_categorical_inputs_remain_pending(self):
        rule,inp=self.fixture();layout=compile_inputs(rule)
        inp['numbers'][0,2]=np.inf;inp['numeric'][1,2]=False
        result,marks=encode_inputs(inp,layout,np)
        self.assertFalse(result['input_ready'].any())
        inp['scalar_codes'][1,2]=scalar(dict(sort='i64',value=-9));inp['scalar_valid'][1,2]=True
        result,_=encode_inputs(inp,layout,np);self.assertEqual(result['input_ready'].tolist(),[False,True])


if __name__=='__main__':unittest.main()

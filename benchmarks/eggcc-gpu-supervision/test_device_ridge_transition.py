import unittest
import numpy as np
import mlx.core as mx
from device_ridge_transition import infer,proposals
from device_token_commit import commit
from multi_entry_ridge import features


def fixture():
    rng=np.random.default_rng(89);n=3;d=128;c=4;q=64
    s=dict(tokens=rng.normal(size=(n,d)).astype(np.float32),keys=np.array([[0,7],[-1,-1],[-1,-1]],np.int32),
        generation=np.ones(n,np.int32))
    for k in ('present','visible','settled','active'):s[k]=np.array([True,False,False])
    s['readers']=np.zeros(n,bool);s['token_dirty']=np.zeros(n,bool)
    r=dict(sources=np.zeros((n,2),np.int32),generations=np.ones((n,2),np.int32),edge_valid=np.array([[True,False]]*n),
        edge=rng.normal(size=(n,2,d)).astype(np.float32),route=rng.normal(size=(n,2,c)).astype(np.float32),
        seed=rng.normal(size=(n,d)).astype(np.float32),q=rng.normal(size=(n,q)).astype(np.float32),input_ready=np.ones(n,bool))
    raw=d+q+2*c*d
    m=dict(w=rng.normal(0,.02,(raw,16)).astype(np.float32),coef=rng.normal(0,.02,(1+raw+16,d)).astype(np.float32))
    return s,r,m


class RidgeTransition(unittest.TestCase):
    def test_matches_existing_feature_map(self):
        s,r,m=fixture();out,marks=infer(s,r,m,np)
        pool=np.stack([np.outer(r['route'][i,0],s['tokens'][0]*r['edge'][i,0]).reshape(-1) for i in range(3)])
        expected=np.tanh(features(r['seed'],r['q'],pool,m['w'],np)@m['coef'])
        np.testing.assert_allclose(out,expected,atol=1e-6);self.assertTrue(marks['ready'].all())

    def test_generation_dirty_and_missing_inputs(self):
        for cause in ('generation','token_dirty','visible','settled','input_ready'):
            s,r,m=fixture()
            if cause=='input_ready':r[cause][0]=False
            elif cause=='generation':s[cause][0]+=1
            else:s[cause][0]=(cause=='token_dirty')
            _,marks=infer(s,r,m,np);self.assertFalse(marks['ready'][0]);self.assertTrue(marks['needs_attention'])
        s,r,m=fixture();s['active'][0]=False
        self.assertTrue(infer(s,r,m,np)[1]['ready'].all()) # shared source remains readable

    def test_padding_and_nonfinite_live_sources(self):
        s,r,m=fixture();r['sources'][:,1]=-999;r['edge'][:,1]=np.nan;r['route'][:,1]=np.nan
        out,marks=infer(s,r,m,np);self.assertTrue(np.isfinite(out).all());self.assertTrue(marks['ready'].all())
        s['tokens'][0,0]=np.nan
        self.assertFalse(infer(s,r,m,np)[1]['ready'].any())

    def test_gpu_inference_directly_admits_tokens_without_test_weights(self):
        if not mx.metal.is_available():self.skipTest('Metal required')
        s,r,m=fixture()
        plan=dict(producer=np.array([0],np.int32),consumer=np.array([1],np.int32),stage=np.array([0],np.int32),
            projection=np.array([[1]],np.int32),query_covered=np.array([True]),transfer_covered=np.array([False]),completed=np.array([False]))
        dev=lambda x:{k:mx.array(v) for k,v in x.items()}
        dp,dr,dm=dev(plan),dev(r),dev(m)
        def run(state):
            p,n=proposals(state,dp,mx.array(0),dr,dm,mx)
            out,a=commit(state,p,mx)
            return out,a,n
        out,a,n=mx.compile(run)(dev(s));mx.eval(out,a,n)
        expected,_=infer(s,r,m,np)
        self.assertEqual(np.array(a['accepted']).tolist(),[True,False,False])
        np.testing.assert_allclose(np.array(out['tokens'])[1],expected[0],atol=2e-6)
        self.assertFalse(np.array(out['settled'])[1]) # prediction grants no effect proof


if __name__=='__main__':unittest.main()

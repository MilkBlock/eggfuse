import unittest
from copy import deepcopy
import numpy as np
import mlx.core as mx
from test_device_join_transition import fixture
from test_device_query_join import fixture as recipe_fixture
from device_join_transition import step
from device_boundary_context import compile_context
from device_match_capture import floating_inputs,host,audit
from audit_snapshot_queries import device


class LiveBoundaryModel(unittest.TestCase):
    def fixture(self):
        s,p,m=fixture();recipe,_=recipe_fixture()
        p['boundary_context']=compile_context(recipe,2,s['slots'].shape[1])
        rng=np.random.default_rng(416)
        m['coef']=np.concatenate([m['coef'],rng.normal(0,.03,(s['slots'].shape[1]*64,128)).astype(np.float32)],axis=0)
        return recipe,s,p,m

    def test_live_features_feed_prediction_and_capture_once(self):
        recipe,s,p,m=self.fixture();out,marks=step(s,p,m,4,True,True,np,capture=True)
        c=marks['capture'];self.assertTrue(audit(recipe,c)['passed'])
        self.assertIs(c['boundary_features'],c['request']['boundary_features'])
        x=floating_inputs(c,m,np);expected=np.tanh(x@m['coef'])
        np.testing.assert_allclose(c['predicted_tokens'],expected,atol=2e-6)
        plain=deepcopy(m);plain['coef']=plain['coef'][:1+m['w'].shape[0]+m['w'].shape[1]]
        baseline,bm=step(s,p,plain,4,True,True,np,capture=True)
        self.assertGreater(np.linalg.norm(out['tokens']-baseline['tokens']),.01)
        for key in out:
            if key!='tokens':np.testing.assert_array_equal(out[key],baseline[key])
        np.testing.assert_array_equal(marks['admission']['accepted'],bm['admission']['accepted'])

    def test_wrong_or_missing_layout_rejected(self):
        _,s,p,m=self.fixture();no=dict(p);no.pop('boundary_context')
        with self.assertRaises(ValueError):step(s,no,m,4,True,True,np)
        m['coef']=m['coef'][:-1]
        with self.assertRaises(ValueError):step(s,p,m,4,True,True,np)

    def test_compiled_gpu_uses_same_prediction(self):
        _,s,p,m=self.fixture();ds,dp,dm=map(device,(s,p,m))
        out,marks=mx.compile(lambda state:step(state,dp,dm,4,mx.array(True),mx.array(True),mx,capture=True))(ds)
        mx.eval(out,marks);c=host(marks['capture'])
        expected=np.tanh(floating_inputs(c,m,np)@m['coef'])
        np.testing.assert_allclose(c['predicted_tokens'],expected,atol=2e-6)
        self.assertEqual(int(np.array(marks['admission']['accepted']).sum()),1)

if __name__=='__main__':unittest.main()

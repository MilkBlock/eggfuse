import unittest
from unittest.mock import patch
import numpy as np
import mlx.core as mx
from device_completion_classifier import compile_classifier,apply
from device_completion_states import compile_states
from test_device_join_transition import fixture
from test_device_query_join import fixture as query_fixture
from device_join_transition import proposals
from audit_snapshot_queries import device


class LiveClassifier(unittest.TestCase):
    def fixture(self):
        state,plan,model=fixture();recipe,_=query_fixture();rule=recipe['rules'][2]
        width=model['coef'].shape[0];count=len(compile_states(rule)['states'])
        rng=np.random.default_rng(81)
        head=dict(mean=np.zeros(width,np.float32),scale=np.ones(width,np.float32),
            coef=rng.normal(0,.01,(width,count)).astype(np.float32),bias=np.zeros(count,np.float32))
        plan['completion_classifier']=compile_classifier(rule,head)
        return state,plan,model,rule,head

    def test_old_output_and_decoder_are_absent_and_exact_proposals_unchanged(self):
        s,p,m,_,_=self.fixture();old={k:v for k,v in p.items() if k!='completion_classifier'}
        baseline,_=proposals(s,old,m,4,True,True,np,True)
        model=dict(w=m['w'])
        with patch('device_join_transition.infer',side_effect=AssertionError('old output used')),patch('device_completion_readout.apply',side_effect=AssertionError('decoder used')):
            out,marks=proposals(s,p,model,4,True,True,np,True)
            gpu,gm=mx.compile(lambda state:proposals(state,device(p),device(model),4,mx.array(True),mx.array(True),mx,True))(device(s));mx.eval(gpu,gm)
        for key in baseline:
            if key!='tokens':np.testing.assert_array_equal(out[key],baseline[key],err_msg=key)
        self.assertNotIn('raw_tokens',marks['capture']['completion_readout'])
        np.testing.assert_allclose(gpu['tokens'],out['tokens'],atol=2e-6)
        np.testing.assert_array_equal(gm['capture']['completion_readout']['chosen'],marks['capture']['completion_readout']['chosen'])
        self.assertGreater(np.max(abs(out['tokens']-baseline['tokens'])),.01)

    def test_invalid_layout_nonfinite_inputs_and_source_lifetime(self):
        s,p,m,r,h=self.fixture();bad=dict(h,scale=np.zeros_like(h['scale']))
        with self.assertRaises(ValueError):compile_classifier(r,bad)
        with self.assertRaises(ValueError):compile_classifier(r,dict(h,coef=h['coef'][:,:1]))
        with self.assertRaises(ValueError):proposals(s,dict(p,completion_readout={}),dict(w=m['w']),4,True,True,np)
        candidate,marks=proposals(s,p,dict(w=m['w']),4,True,True,np,True)
        b=marks['capture']['bindings'];detail=marks['capture']['completion_readout']
        values=np.full((4,h['coef'].shape[0]),np.nan,np.float32)
        _,dm=apply(values,b,detail['scalar_codes'],detail['scalar_ready'],p['completion_classifier'],np)
        self.assertFalse(dm['ready'].any())
        s['token_dirty'][1]=True
        blocked,_=proposals(s,p,dict(w=m['w']),4,True,True,np)
        self.assertFalse(blocked['matched'].any())

if __name__=='__main__':unittest.main()

import unittest
import numpy as np
import mlx.core as mx
from device_completion_readout import compile_readout,apply,scalar_inputs
from audit_snapshot_queries import device
from test_completion_states import rule
from test_device_join_transition import fixture
from test_device_query_join import fixture as query_fixture
from device_join_transition import proposals


def decoder():
    rng=np.random.default_rng(17)
    return rng.normal(0,.01,(1024,16)).astype(np.float32),rng.normal(0,.02,(1041,1)).astype(np.float32)


class CompletionReadout(unittest.TestCase):
    def test_live_proposals_replace_tokens_but_not_slots(self):
        state,plan,model=fixture();recipe,_=query_fixture();w,c=decoder()
        baseline,_=proposals(state,plan,model,4,True,True,np,True)
        plan['completion_readout']=compile_readout(recipe['rules'][2],w,c)
        candidate,marks=proposals(state,plan,model,4,True,True,np,True)
        for key in baseline:
            if key!='tokens':np.testing.assert_array_equal(candidate[key],baseline[key],err_msg=key)
        self.assertGreater(np.max(abs(candidate['tokens']-baseline['tokens'])),.01)
        np.testing.assert_array_equal(marks['capture']['completion_readout']['raw_tokens'],baseline['tokens'])
        out,gm=mx.compile(lambda s:proposals(s,device(plan),device(model),4,mx.array(True),mx.array(True),mx,True))(device(state));mx.eval(out,gm)
        np.testing.assert_allclose(out['tokens'],candidate['tokens'],atol=3e-6)
        np.testing.assert_array_equal(gm['capture']['completion_readout']['chosen'],marks['capture']['completion_readout']['chosen'])

    def test_scalar_readiness_and_current_equality(self):
        r=rule(3);r['slots'].append(dict(sort=dict(kind='f64',name='f64'),definition='query'))
        w,c=decoder();plan=compile_readout(r,w,c)
        proposal=dict(tokens=np.zeros((2,128),np.float32),slot_valid=np.ones((2,4),bool),
            scalar_numbers=np.array([[0,0,0,2],[0,0,0,float('nan')]],np.float32),
            scalar_numeric=np.ones((2,4),bool),scalar_codes=np.zeros((2,4,64),np.float32),scalar_valid=np.ones((2,4),bool))
        codes,ready=scalar_inputs(proposal,plan,np)
        self.assertEqual(ready.tolist(),[True,False])
        bindings=dict(slot_roots=np.array([[7,7,9,0],[7,8,9,0]]),slot_valid=proposal['slot_valid'])
        _,marks=apply(proposal['tokens'],bindings,codes,ready,plan,np)
        self.assertTrue(marks['required'][0,0]);self.assertTrue(marks['selected'][0,0]);self.assertFalse(marks['ready'][1])
        bad=proposal['tokens'].copy();bad[0,0]=float('nan')
        _,marks=apply(bad,bindings,codes,ready,plan,np)
        self.assertFalse(marks['ready'].any())
        r['slots'][3]['definition']='effect'
        with self.assertRaises(ValueError):compile_readout(r,w,c)

if __name__=='__main__':unittest.main()

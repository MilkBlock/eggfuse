import unittest
import numpy as np
import mlx.core as mx
from test_device_query_join import fixture,device_plan
from device_query_join import compile_query,order_query,match


class QueryOrder(unittest.TestCase):
    def test_selective_order_avoids_prefix_overflow_and_preserves_original_origin(self):
        recipe,state=fixture()
        state={k:np.concatenate([v,v[:1],v[:1]],axis=0) for k,v in state.items()}
        state['slots'][2:]=[[8,101,-1],[9,102,-1]];state['slot_roots'][2:]=[[8,11,-1],[9,12,-1]]
        original=compile_query(recipe,2);ordered=order_query(original,{0:3,1:1})
        self.assertEqual(ordered['order'],[1,0]);self.assertNotIn('order',original)
        self.assertFalse(match(state,original,1,True,True,np)['complete'])
        expected=match(state,original,4,True,True,np)
        plan=device_plan(ordered);ds={k:mx.array(v) for k,v in state.items()}
        actual=mx.compile(lambda s:match(s,plan,1,mx.array(True),mx.array(True),mx))(ds);mx.eval(actual)
        self.assertTrue(bool(actual['complete']));self.assertFalse(bool(actual['overflow']))
        for key in ('slots','slot_roots','source_rows','source_slots','source_generations','witness_rows','witness_records','witness_generations'):
            np.testing.assert_array_equal(np.array(actual[key])[0],expected[key][np.flatnonzero(expected['live'])[0]])
        self.assertEqual(int(actual['slots'][0,1]),100) # not G's equivalent raw ID 99

    def test_invalid_order_or_estimate_cannot_drop_atoms(self):
        recipe,state=fixture();plan=compile_query(recipe,2)
        with self.assertRaises(ValueError):match(state,dict(plan,order=[1]),1,True,True,np)
        with self.assertRaises(ValueError):match(state,dict(plan,order=[0,0]),1,True,True,np)
        with self.assertRaises(ValueError):order_query(plan,{0:-1,1:2})

if __name__=='__main__':unittest.main()

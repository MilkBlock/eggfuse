import unittest
import numpy as np
import mlx.core as mx
from device_alias_completion import compile_rule,compile_completion,complete
from test_lower_device_entries import recipe
from lower_device_entries import lower,tensors
from cell_token_successors import compile_catalog
from device_token_commit import commit,closed_entry_proposals


class AliasCompletion(unittest.TestCase):
    def test_no_circular_proof_from_later_union(self):
        r=recipe();rule=r['rules'][0]
        tables={t['name']:t for t in r['tables']}
        p=compile_rule(rule,tables)
        self.assertTrue(p['covered']);self.assertEqual(p['projection'][2],1)
        rule['effects']=[dict(kind='union',args=[dict(slot=0),dict(slot=1)]),*rule['effects']]
        self.assertEqual(compile_rule(rule,tables)['reason'],'new_equality')

    def test_constructor_not_in_query_is_pending(self):
        r=recipe(True);p=compile_rule(r['rules'][0],{t['name']:t for t in r['tables']})
        self.assertFalse(p['covered'])

    def test_gpu_effect_completion_then_continuation_without_host_read(self):
        if not mx.metal.is_available():self.skipTest('Metal required')
        mx.set_default_device(mx.gpu)
        r=recipe();effect_plan,proofs=compile_completion(r)
        layout=lower(r,compile_catalog(r),source_slots=True)
        entries=tensors(layout,np.array([np.eye(3)],np.float32),np.zeros((1,3),np.float32))
        ep={k:mx.array(v) for k,v in effect_plan.items()};dp={k:mx.array(v) for k,v in entries.items()}
        def state(valid):
            return dict(keys=mx.array([[0,41,999],[-1,-1,-1]],mx.int32),tokens=mx.array([[.2,.3,.4],[0.,0.,0.]]),
                slots=mx.array([[41,999,-1],[-1,-1,-1]],mx.int32),slot_valid=mx.array([[True,valid,False],[False,False,False]]),
                present=mx.array([True,False]),active=mx.array([True,False]),visible=mx.array([True,False]),
                settled=mx.array([False,False]),readers=mx.array([False,False]),generation=mx.array([1,0],mx.int32))
        def run(s):
            s,e=complete(s,ep,mx)
            s,a=commit(s,closed_entry_proposals(s,dp,mx.array(0),mx),mx)
            return s,e,a
        out,e,a=mx.compile(run)(state(True));mx.eval(out,e,a)
        self.assertTrue(np.array(e['completed'])[0])
        self.assertEqual(int(np.array(out['slots'])[0,2]),999)
        np.testing.assert_array_equal(np.array(out['keys'])[1],[1,41,999])
        self.assertEqual(int(np.array(a['accepted']).sum()),1)
        out,e,a=mx.compile(run)(state(False));mx.eval(out,e,a)
        self.assertFalse(np.array(out['settled'])[0]);self.assertTrue(np.array(e['unavailable'])[0])
        self.assertFalse(np.array(a['accepted']).any())


if __name__=='__main__':unittest.main()

import unittest
import numpy as np
import mlx.core as mx
import test_device_constructor_completion as helper
from cell_token_successors import compile_catalog
from lower_device_entries import lower,tensors
from device_entry_transition import compile_features
from device_constructor_completion import compile_completion
from device_stage_loop import compile_controls,run


class StageLoop(unittest.TestCase):
    def fixture(self):
        recipe=helper.recipe();lowered=lower(recipe,compile_catalog(recipe),source_slots=True);blocks=[]
        for e in lowered['entries']:
            plan=tensors(dict(lowered,entries=[e]),np.zeros((1,128,128)),np.zeros((1,128)));plan.pop('weights');plan.pop('bias')
            # Explicit two-stage local fixture. This is not cross-stage lowering.
            plan['stage'][0]=0 if e['producer']==0 else 1
            il,cl=compile_features(recipe,e);blocks.append((plan,il,cl))
        rng=np.random.default_rng(62);model=dict(w=rng.normal(0,.01,(1408,16)).astype(np.float32),coef=rng.normal(0,.01,(1425,128)).astype(np.float32))
        return helper.state(),blocks,model,compile_completion(recipe,3)

    def test_device_generates_completes_then_advances_two_local_stages(self):
        if not mx.metal.is_available():self.skipTest('Metal required')
        s,b,m,p=self.fixture();dev=lambda d:{k:mx.array(v) for k,v in d.items()}
        db=[tuple(dev(x) for x in block) for block in b];dm=dev(m);dp=helper.device_plan(p)
        # Fixture coverage is assumed over its explicitly enumerated local family.
        controls=dict(schedule=mx.array([0,1]),query_covered=mx.array([True,True]))
        out,n,marks=mx.compile(lambda state:run(state,db,dm,dp,controls,mx.array(100),mx.array(200),mx.array(100),mx.array(True),mx.array(True),5,mx))(dev(s));mx.eval(out,n,marks)
        self.assertEqual(np.array(marks['new_tokens']).tolist(),[1,0,1,0,0])
        self.assertEqual(np.array(marks['stage_history']).tolist(),[0,0,1,1,-1])
        self.assertTrue(bool(marks['finished']));self.assertEqual(int(n),102)
        np.testing.assert_array_equal(np.array(out['keys'])[2],[2,100,101])

    def test_real_lowering_defaults_to_uncovered_and_does_not_advance(self):
        s,b,m,p=self.fixture();recipe=helper.recipe();lowered=lower(recipe,compile_catalog(recipe),source_slots=True)
        controls=compile_controls(lowered,[0])
        out,n,marks=run(s,b,m,p,controls,np.array(100),np.array(200),np.array(100),np.array(True),np.array(True),3,np)
        self.assertFalse(marks['finished']);self.assertEqual(marks['stage_cursor'],0)
        self.assertEqual(marks['new_tokens'].tolist(),[1,0,0]);self.assertTrue(marks['needs_attention'][-1])

    def test_capacity_external_boundary_and_budget_prevent_advancement(self):
        for mode in ('capacity','external','budget'):
            s,b,m,p=self.fixture();controls=dict(schedule=np.array([0,1]),query_covered=np.array([True,True]))
            if mode=='capacity':s={k:v[:1] for k,v in s.items()}
            out,n,marks=run(s,b,m,p,controls,np.array(100),np.array(200),np.array(100),np.array(mode!='external'),np.array(True),1 if mode=='budget' else 3,np)
            self.assertFalse(marks['finished']);self.assertTrue(marks['round_budget_consumed'])
            self.assertEqual(marks['stage_cursor'],0)


if __name__=='__main__':unittest.main()

import unittest
from unittest.mock import patch
import numpy as np
import mlx.core as mx
import test_live_completion_classifier as fixtures
from test_device_query_join import fixture as recipe_fixture
from device_boundary_context import compile_context
from device_completion_classifier import compile_classifier
from device_join_transition import run_round
from bake_boundary_groups import group_boundary_plans
from audit_snapshot_queries import device

class BoundaryGroups(unittest.TestCase):
    def fixture(self):
        s,p,m,r,h=fixtures.LiveClassifier().fixture();recipe,_=recipe_fixture();width=s['slots'].shape[1]
        p['boundary_context']=compile_context(recipe,2,width);p['shared_boundary_context']=True
        extra=width*32*3
        h=dict(h,mean=np.pad(h['mean'],(0,extra)),scale=np.pad(h['scale'],(0,extra),constant_values=1),coef=np.pad(h['coef'],((0,extra),(0,0))))
        p['completion_classifier']=compile_classifier(r,h)
        return s,[(0,p),(0,dict(p))],m

    def test_groups_ignore_only_query_ports_and_split_different_weights(self):
        _,blocks,_=self.fixture();a=blocks[0][1];b=dict(a,boundary_context=dict(a['boundary_context']))
        b['boundary_context']['ports']=b['boundary_context']['ports'][::-1].copy()
        grouped=group_boundary_plans([(0,a),(1,b)])
        self.assertEqual(grouped[0][1]['boundary_group'],grouped[1][1]['boundary_group'])
        b['boundary_context']['token_weight']=b['boundary_context']['token_weight']+1
        grouped=group_boundary_plans([(0,a),(1,b)])
        self.assertNotEqual(grouped[0][1]['boundary_group'],grouped[1][1]['boundary_group'])

    def test_one_preparation_per_group_and_fresh_each_run(self):
        import device_boundary_context as base
        import device_boundary_shared_context as shared
        s,blocks,m=self.fixture();grouped=group_boundary_plans(blocks)
        with patch.object(base,'prepare',wraps=base.prepare) as bp,patch.object(shared,'prepare',wraps=shared.prepare) as sp:
            plain,pm=run_round(s,blocks,m,np.array(0),np,4,True,True,capture=True)
            self.assertEqual((bp.call_count,sp.call_count),(2,2))
        with patch.object(base,'prepare',wraps=base.prepare) as bp,patch.object(shared,'prepare',wraps=shared.prepare) as sp:
            out,marks=run_round(s,grouped,m,np.array(0),np,4,True,True,capture=True)
            self.assertEqual((bp.call_count,sp.call_count),(1,1))
            changed=dict(s,tokens=s['tokens']+.2)
            run_round(changed,grouped,m,np.array(0),np,4,True,True)
            self.assertEqual((bp.call_count,sp.call_count),(2,2))
        for key in out:np.testing.assert_array_equal(out[key],plain[key])
        for x,y in zip(marks['captures'],pm['captures']):
            np.testing.assert_array_equal(x['predicted_tokens'],y['predicted_tokens'])
            np.testing.assert_array_equal(x['request']['shared_boundary_features'],y['request']['shared_boundary_features'])
        gpu,gm=mx.compile(lambda v:run_round(v,device(grouped),device(m),mx.array(0),mx,4,mx.array(True),mx.array(True),capture=True))(device(s));mx.eval(gpu,gm)
        for key in out:
            if np.issubdtype(out[key].dtype,np.floating):np.testing.assert_allclose(gpu[key],out[key],atol=3e-6)
            else:np.testing.assert_array_equal(gpu[key],out[key])

if __name__=='__main__':unittest.main()

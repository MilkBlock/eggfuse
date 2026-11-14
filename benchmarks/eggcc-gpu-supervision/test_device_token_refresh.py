import unittest
import numpy as np
import mlx.core as mx
from multi_entry_ridge import encode,scalar
from device_token_refresh import encode_batch,refresh
from device_eq_completion import close
from device_token_commit import commit,closed_entry_proposals


class TokenRefresh(unittest.TestCase):
    def test_encoding_matches_ridge_representation_with_sorts_scalars_and_padding(self):
        rng=np.random.default_rng(44);roles=rng.normal(size=(3,5,64)).astype(np.float32)
        roots=np.array([[7,7,7,0,-1],[8,9,8,0,-1],[0,0,0,0,0]],np.int32)
        sorts=np.array([[0,0,1,2,0]]*3,np.int32);eq=np.array([[True,True,True,False,True]]*3)
        valid=np.array([[True,True,True,True,False],[True]*4+[False],[False]*5])
        scalar_codes=np.zeros((3,5,64),np.float32)
        scalar_codes[:,3]=scalar(dict(sort='i64',value=3))
        scalar_codes[:,4]=np.nan # Masked padding must not poison output.
        expected=[]
        for row in range(3):
            rows=[(i,dict(sort='i64',value=3), (int(sorts[row,i]),int(roots[row,i])) if eq[row,i] else None) for i in range(5) if valid[row,i]]
            expected.append(encode(rows,roles[row],'class-balanced'))
        actual=encode_batch(roots,sorts,eq,valid,roles,scalar_codes,np)
        np.testing.assert_allclose(actual,expected,atol=2e-6)
        if mx.metal.is_available():
            values=[mx.array(x) for x in (roots,sorts,eq,valid,roles,scalar_codes)]
            gpu=mx.compile(lambda *xs:encode_batch(*xs,mx))(*values);mx.eval(gpu)
            np.testing.assert_allclose(np.array(gpu),expected,atol=2e-6)

    def setup_state(self):
        return dict(keys=np.array([[0,1,2],[-1,-1,-1]],np.int32),slots=np.array([[1,2],[-1,-1]],np.int32),
            slot_valid=np.array([[True,True],[False,False]]),present=np.array([True,False]),active=np.array([True,False]),
            visible=np.array([True,False]),settled=np.array([True,False]),readers=np.array([False,False]),
            generation=np.array([1,0],np.int32),effect_pc=np.array([0,0],np.int32),tokens=np.zeros((2,128),np.float32))

    def test_eq_close_refresh_then_successor_without_host_read(self):
        if not mx.metal.is_available():self.skipTest('Metal required')
        mx.set_default_device(mx.gpu)
        roles=mx.array(np.random.default_rng(45).normal(size=(2,2,64)).astype(np.float32))
        plan={k:mx.array(v) for k,v in dict(producer=np.array([0],np.int32),consumer=np.array([1],np.int32),stage=np.array([0],np.int32),
            projection=np.array([[1,2]],np.int32),query_covered=np.array([True]),transfer_covered=np.array([False]),completed=np.array([True]),
            weights=np.array([np.eye(128)*.7],np.float32),bias=np.zeros((1,128),np.float32)).items()}
        # A source-slot layout preserves exact witnesses and roots across admission.
        plan['destination_projection']=mx.array([[0,1]],mx.int32)
        plan['destination_valid']=mx.array([[True,True]])
        plan['projection']=mx.array([[0,1]],mx.int32)
        plan['projection_valid']=mx.array([[True,True]])
        def integrated(s):
            s,roots,c=close(s,mx.arange(4,dtype=mx.int32),mx.zeros(4,mx.int32),mx.ones((2,2),mx.bool_),mx.array([[1,2]],mx.int32),mx.array([True]),[],mx.array(True),3,mx)
            _,blocked=commit(s,closed_entry_proposals(s,plan,mx.array(0),mx),mx)
            s,u=refresh(s,mx.zeros((2,2),mx.int32),mx.ones((2,2),mx.bool_),mx.ones((2,2),mx.bool_),roles,mx.zeros((2,2,64)),mx.ones((2,2),mx.bool_),c['settled'],mx)
            s,a=commit(s,closed_entry_proposals(s,plan,mx.array(0),mx),mx)
            return s,blocked,u,a
        out,b,u,a=mx.compile(integrated)({k:mx.array(v) for k,v in self.setup_state().items()});mx.eval(out,b,u,a)
        self.assertFalse(np.array(b['accepted']).any());self.assertTrue(np.array(u['refreshed'])[0])
        self.assertEqual(np.array(a['accepted']).sum(),1);self.assertFalse(np.array(out['token_dirty']).any())
        self.assertGreater(float(np.linalg.norm(np.array(out['tokens'])[1])),.01)

    def test_experimental_feedback_preserves_prediction_but_not_readiness_bypasses(self):
        for mode in ('ready','slot','eq','nonfinite','unsettled','hidden'):
            state=self.setup_state();state['token_dirty']=np.array([True,False])
            state['tokens'][0]=.123
            if mode=='slot':state['slot_valid'][0,1]=False
            if mode=='nonfinite':state['tokens'][0,0]=np.nan
            if mode=='unsettled':state['settled'][0]=False
            if mode=='hidden':state['visible'][0]=False
            out,marks=refresh(state,np.zeros((2,2),np.int32),np.ones((2,2),bool),np.ones((2,2),bool),np.zeros((2,2,64),np.float32),np.zeros((2,2,64),np.float32),np.ones((2,2),bool),mode!='eq',np,retain_prediction=True)
            np.testing.assert_array_equal(out['tokens'],state['tokens'])
            self.assertEqual(bool(marks['refreshed'][0]),mode=='ready')
            self.assertEqual(bool(out['token_dirty'][0]),mode!='ready')

    def test_missing_fields_or_unsettled_eq_cannot_clear_dirty(self):
        roles=np.zeros((2,2,64),np.float32)
        for mode in ('slot','scalar','eq'):
            s=self.setup_state();s['token_dirty']=np.array([True,False])
            eq=np.ones((2,2),bool);codes=np.zeros((2,2,64),np.float32);scalar_valid=np.ones((2,2),bool)
            if mode=='slot':s['slot_valid'][0,1]=False
            if mode=='scalar':eq[0,1]=False;scalar_valid[0,1]=False
            out,m=refresh(s,np.zeros((2,2),np.int32),eq,np.ones((2,2),bool),roles,codes,scalar_valid,mode!='eq',np)
            self.assertTrue(out['token_dirty'][0]);self.assertFalse(m['refreshed'][0])


if __name__=='__main__':unittest.main()

import unittest
import numpy as np
import mlx.core as mx
from test_lower_device_entries import recipe
from cell_token_successors import compile_catalog
from lower_device_entries import lower,tensors
from device_entry_transition import compile_features,step


class EntryTransition(unittest.TestCase):
    def fixture(self):
        r=recipe(True);lowered=lower(r,compile_catalog(r),source_slots=True)
        entry=lowered['entries'][0];features,coeff=compile_features(r,entry)
        plan=tensors(lowered,np.zeros((1,128,128),np.float32),np.zeros((1,128),np.float32))
        plan.pop('weights');plan.pop('bias')
        rng=np.random.default_rng(61)
        model=dict(w=rng.normal(0,.01,(1408,16)).astype(np.float32),coef=rng.normal(0,.01,(1425,128)).astype(np.float32))
        s=dict(keys=np.array([[0,41,72],[-1,-1,-1],[-1,-1,-1]],np.int32),tokens=rng.normal(0,.1,(3,128)).astype(np.float32),
            slots=np.array([[41,72,999],[-1,-1,-1],[-1,-1,-1]],np.int32),slot_roots=np.array([[41,72,41],[-1,-1,-1],[-1,-1,-1]],np.int32),
            slot_valid=np.array([[True]*3,[False]*3,[False]*3]),generation=np.array([1,0,0],np.int32))
        for k in ('present','visible','active','settled'):s[k]=np.array([True,False,False])
        for k in ('readers','token_dirty'):s[k]=np.zeros(3,bool)
        return s,plan,features,coeff,model

    def test_gpu_matches_projects_encodes_and_admits_actual_result(self):
        if not mx.metal.is_available():self.skipTest('Metal required')
        s,p,f,c,m=self.fixture();dev=lambda d:{k:mx.array(v) for k,v in d.items()}
        ds,dp,df,dc,dm=map(dev,(s,p,f,c,m))
        def run(state):
            out,first=step(state,dp,df,dc,dm,mx.array(0),mx)
            out,second=step(out,dp,df,dc,dm,mx.array(0),mx)
            return out,first,second
        out,first,second=mx.compile(run)(ds);mx.eval(out,first,second)
        self.assertEqual(np.array(out['keys'])[1].tolist(),[1,41,999])
        self.assertEqual(np.array(out['slot_roots'])[1,:2].tolist(),[41,41])
        self.assertEqual(np.array(first['admission']['accepted']).sum(),1)
        self.assertEqual(np.array(second['admission']['accepted']).sum(),0)
        self.assertFalse(np.array(first['admission']['transferred']).any())
        expected,_=step(s,p,f,c,m,np.array(0),np)
        np.testing.assert_allclose(np.array(out['tokens'])[1],expected['tokens'][1],atol=2e-6)
        changed=dict(s,slot_roots=s['slot_roots'].copy());changed['slot_roots'][0,2]=999
        other,_=step(changed,p,f,c,m,np.array(0),np)
        self.assertGreater(np.max(np.abs(other['tokens'][1]-expected['tokens'][1])),1e-5)

    def test_missing_result_dirty_source_and_wrong_stage_do_not_admit(self):
        for mode in ('result','dirty','stage'):
            s,p,f,c,m=self.fixture()
            if mode=='result':s['slot_valid'][0,2]=False
            if mode=='dirty':s['token_dirty'][0]=True
            out,marks=step(s,p,f,c,m,np.array(1 if mode=='stage' else 0),np)
            self.assertFalse(marks['admission']['accepted'].any())
            self.assertEqual(out['present'].sum(),1)

    def test_scalar_columns_follow_same_projected_slots(self):
        s,p,f,c,m=self.fixture()
        s['scalar_numbers']=np.array([[3,5,9],[0,0,0],[0,0,0]],np.float32)
        s['scalar_numeric']=np.ones((3,3),bool);s['scalar_codes']=np.zeros((3,3,64),np.float32);s['scalar_valid']=np.ones((3,3),bool)
        out,marks=step(s,p,f,c,m,np.array(0),np)
        self.assertTrue(marks['admission']['accepted'][0])
        np.testing.assert_array_equal(out['scalar_numbers'][1],[3,9,0])
        self.assertFalse(out['scalar_valid'][1,2])


if __name__=='__main__':unittest.main()

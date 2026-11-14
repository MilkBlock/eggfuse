import unittest
import numpy as np
import mlx.core as mx
from audit_snapshot_queries import device
from device_matched_takeover import compile_catalog,initialize,finish
from device_slot_owners import pack,read
from device_join_transition import step
from test_device_join_transition import fixture
from test_device_query_join import fixture as recipe_fixture

class SharedAtomTakeover(unittest.TestCase):
    def test_shared_atom_variables_enable_original_width_gpu_transfer(self):
        recipe,_=recipe_fixture();s,p,m=fixture();s['readers'][:]=False
        s['slots'][1,0]=s['slots'][0,1];s['keys'][1,1]=s['slots'][1,0]
        blocks,catalog,atoms=compile_catalog(recipe,[(0,p)],3)
        packed=initialize(pack(s),atoms);dp=device(blocks[0][1]);dm=device(m)
        def run(state):
            matched,_=step(state,dp,dm,4,mx.array(True),mx.array(True),mx)
            return finish(matched,catalog,mx.array(True),mx)
        out,marks=mx.compile(run)(device(packed));mx.eval(out,marks)
        self.assertEqual(int(marks['released']),2);self.assertEqual(int(marks['copied_fields']),0)
        out={k:np.array(v) for k,v in out.items()}
        np.testing.assert_array_equal(read(out,'slots',np.array(0),np.array([0,1]),np),s['slots'][0,:2])
        np.testing.assert_array_equal(read(out,'slots',np.array(1),np.array([0,1]),np),s['slots'][1,:2])

    def test_eq_only_binding_cannot_authorize_value_alias(self):
        recipe,_=recipe_fixture();s,p,m=fixture();s['readers'][:]=False
        blocks,catalog,atoms=compile_catalog(recipe,[(0,p)],3)
        matched,_=step(initialize(pack(s),atoms),blocks[0][1],m,4,True,True,np)
        out,marks=finish(matched,catalog,np.array(True),np,diagnostics=True)
        self.assertEqual(marks['released'],1)
        self.assertEqual(marks['blocked_reasons']['value_mismatch'],1)
        np.testing.assert_array_equal(read(out,'slots',np.array(1),np.array([0,1]),np),s['slots'][1,:2])

    def test_raw_identity_mismatch_preserves_existing_copy_plan(self):
        recipe,_=recipe_fixture();s,p,m=fixture();s['readers'][:]=False
        for key in ('slots','slot_roots','slot_valid'):
            s[key]=np.pad(s[key],((0,0),(0,1)),constant_values=False if key=='slot_valid' else -1)
        blocks,catalog,atoms=compile_catalog(recipe,[(0,p)],4)
        matched,_=step(initialize(pack(s),atoms),blocks[0][1],m,4,True,True,np)
        out,marks=finish(matched,catalog,np.array(True),np)
        self.assertEqual(marks['released'],2);self.assertEqual(marks['copied_fields'],1)
        self.assertNotEqual(read(out,'slots',np.array(0),np.array(1),np),read(out,'slots',np.array(1),np.array(0),np))

if __name__=='__main__':unittest.main()

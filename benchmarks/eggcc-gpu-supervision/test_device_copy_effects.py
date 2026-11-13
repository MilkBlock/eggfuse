import unittest
import numpy as np
import mlx.core as mx
from device_copy_effects import compile_copies,execute_copy
from device_constructor_completion import compile_completion,complete
import test_device_constructor_completion as fixture


class CopyEffects(unittest.TestCase):
    def test_exact_identity_root_and_scalar_columns_follow_source(self):
        s=fixture.state();s['slot_roots'][0,0]=5
        s['scalar_numbers']=np.array([[3,0,0],[0,0,0],[0,0,0]],np.float32)
        s['scalar_numeric']=np.ones((3,3),bool);s['scalar_valid']=np.ones((3,3),bool)
        s['scalar_codes']=np.arange(3*3*64,dtype=np.float32).reshape(3,3,64)
        site=dict(rule=0,operation=0,src=0,dst=1,last_effect=True)
        out,m=execute_copy(s,site,np)
        self.assertEqual(out['slots'][0,1],7);self.assertEqual(out['slot_roots'][0,1],5)
        self.assertEqual(out['scalar_numbers'][0,1],3);np.testing.assert_array_equal(out['scalar_codes'][0,1],s['scalar_codes'][0,0])
        self.assertTrue(out['settled'][0]);self.assertTrue(out['token_dirty'][0])
        missing=dict(site,src=2);blocked,m=execute_copy(s,missing,np)
        self.assertTrue(m['missing_source'][0]);self.assertEqual(blocked['effect_pc'][0],0)

    def test_copy_then_constructor_and_refresh_in_one_gpu_call(self):
        if not mx.metal.is_available():self.skipTest('Metal required')
        r=fixture.recipe();rule=r['rules'][0]
        rule['slots']=r['rules'][1]['slots'].copy();rule['slots'][1]=dict(rule['slots'][1],definition='effect')
        rule['effects']=[dict(kind='copy',arg=dict(slot=0),dst=1),dict(kind='construct',call=dict(table='F'),args=[dict(slot=1)],dst=2)]
        plan=fixture.device_plan(compile_completion(r,3))
        dev=lambda x:{k:mx.array(v) for k,v in x.items()}
        out,n,m=mx.compile(lambda state:complete(state,plan,mx.array(100),mx.array(200),mx.array(100),mx.array(True),mx.array(True),mx))(dev(fixture.state()));mx.eval(out,n,m)
        np.testing.assert_array_equal(np.array(out['slots'])[0],[7,7,100]);self.assertEqual(int(n),101)
        self.assertEqual(int(m['executed']),2);self.assertEqual(int(m['refreshed']),1)
        self.assertTrue(np.array(out['settled'])[0]);self.assertFalse(np.array(out['token_dirty'])[0])

    def test_copy_only_refresh_and_invalid_compile(self):
        r=fixture.recipe();r['rules'][0]['effects']=[dict(kind='copy',arg=dict(slot=0),dst=1)]
        out,n,m=complete(fixture.state(),compile_completion(r,3),np.array(100),np.array(200),np.array(100),np.array(False),np.array(True),np)
        self.assertEqual(n,100);self.assertTrue(out['settled'][0]);self.assertFalse(out['token_dirty'][0])
        self.assertFalse(m['semantic_changed'])
        self.assertEqual(m['refreshed'],1) # Copy itself needs no external constructor view.
        r['rules'][0]['slots'][1]['sort']=dict(kind='primitive',name='i64')
        with self.assertRaisesRegex(ValueError,'sort mismatch'):compile_copies(r)


if __name__=='__main__':unittest.main()

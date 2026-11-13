import unittest
import numpy as np
import mlx.core as mx
from bake_stop_features import plan,pack,evaluate,NAMES
from boundary_cell_ridge import D,B
from test_cell_token_successors import rule,atom,make


class StopFeatures(unittest.TestCase):
    def test_output_energy_reads_current_reserved_slots_only(self):
        a,b,new=('input',0),('input',1),('completion',0,0)
        r=rule([atom('F',0,1)],[make('G',2,1)],2)
        wiring=pack([plan([('F',(a,b))],r,[(0,a),(1,b)],[a,b,new],3)])
        s=np.zeros((1,D+3*B),np.float32);s[:,D:D+2*B]=100
        before=evaluate(s,*wiring,np)
        self.assertEqual(before[0,2],0)
        s[:,D+2*B:]=2
        after=evaluate(s,*wiring,np)
        self.assertEqual(after[0,2],4);self.assertEqual(after[0,3],2)
        device=evaluate(mx.array(s),*[mx.array(v) for v in wiring],mx);mx.eval(device)
        np.testing.assert_allclose(np.array(device),after,atol=1e-6)

    def test_direct_union_tracks_copy_aliases_but_not_fresh_results(self):
        a,b=('input',0),('input',1);source=[('F',(a,b))]
        r=rule([atom('F',0,1)],[dict(kind='copy',dst=2,arg=dict(slot=0)),dict(kind='union',args=[dict(slot=2),dict(slot=1)])],2)
        _,pairs=plan(source,r,[(0,a),(1,b)],[a,b],2)
        self.assertEqual(pairs,[(0,1)])
        r['effects'][0]=make('G',2,0)
        _,pairs=plan(source,r,[(0,a),(1,b)],[a,b],2)
        self.assertEqual(pairs,[])

    def test_equal_channel_vectors_are_only_a_hint_not_a_union_proof(self):
        a,b=('input',0),('input',1)
        r=rule([atom('F',0,1)],[dict(kind='union',args=[dict(slot=0),dict(slot=1)])],2)
        wiring=pack([plan([('F',(a,b))],r,[(0,a),(1,b)],[a,b],2)])
        self.assertNotEqual(wiring[1][0,0],wiring[2][0,0])
        values=evaluate(np.ones((1,D+2*B),np.float32),*wiring,np)
        self.assertEqual(values.shape[1],len(NAMES));self.assertEqual(values[0,-1],0)

if __name__=='__main__':unittest.main()

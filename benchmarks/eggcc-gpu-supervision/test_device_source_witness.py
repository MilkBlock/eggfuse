import unittest
import numpy as np
import mlx.core as mx
from device_source_witness import compile_sites,lookup


class Witness(unittest.TestCase):
    def test_selected_source_and_generation_are_authoritative(self):
        eq=dict(kind='eq',name='E')
        source=dict(query=[dict(call=dict(table='F'),args=[dict(slot=0),dict(slot=1)])],effects=[])
        target=dict(query=[],effects=[dict(kind='construct',call=dict(table='F'),args=[dict(slot=0)],dst=1)])
        recipe=dict(tables=[dict(name='F',kind='constructor')],rules=[source,target])
        site=compile_sites(recipe,target)[1]
        state=dict(slots=mx.array([[4,5],[6,7]]),slot_roots=mx.array([[0,1],[0,2]]),slot_valid=mx.ones((2,2),mx.bool_),
                   keys=mx.array([[0],[0]]),present=mx.array([True,True]),visible=mx.array([True,True]),settled=mx.array([True,True]),
                   generation=mx.array([2,3]),effect_pc=mx.array([0,0]))
        payload=dict(slot_roots=mx.array([[0,-1]]),slot_valid=mx.array([[True,False]]))
        batch=dict(sources=mx.array([[0]]),mask=mx.array([[True]]),generations=mx.array([[2]]))
        found,identity,root=lookup(state,payload,batch,0,site,mx)
        self.assertTrue(bool(found));self.assertEqual(int(identity),5);self.assertEqual(int(root),1)
        for bad in [dict(batch,generations=mx.array([[1]])),dict(batch,mask=mx.array([[False]]))]:
            self.assertFalse(bool(lookup(state,payload,bad,0,site,mx)[0]))
        # An unselected live matching row does not rescue a retired source.
        hidden=dict(state,visible=mx.array([False,True]))
        self.assertFalse(bool(lookup(hidden,payload,batch,0,site,mx)[0]))
        mismatch=dict(payload,slot_roots=mx.array([[9,-1]]))
        self.assertFalse(bool(lookup(state,mismatch,batch,0,site,mx)[0]))


if __name__=='__main__':unittest.main()

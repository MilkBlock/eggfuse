import unittest
import numpy as np
import mlx.core as mx
from device_cell_conditions import compile_conditions,activate


class Conditions(unittest.TestCase):
    def test_multi_argument_condition_and_mask(self):
        eq=dict(kind='eq',name='E')
        rule=dict(slots=[dict(sort=eq)]*6,effects=[],query=[
            dict(call=dict(table='F'),args=[dict(slot=i) for i in (0,1,2)]),
            dict(call=dict(table='F'),args=[dict(slot=i) for i in (3,4,5)])])
        plan=compile_conditions(dict(tables=[dict(name='F',kind='constructor')]),rule,6)
        for xp in (np,mx):
            valid=xp.array([True]*6)
            self.assertFalse(bool(activate(plan,xp.array([0,1,2,0,4,5]),valid,xp)[2,5]))
            self.assertTrue(bool(activate(plan,xp.array([0,1,2,0,1,5]),valid,xp)[2,5]))
            self.assertFalse(bool(activate(plan,xp.array([0,1,2,0,1,5]),xp.array([True]*5+[False]),xp)[2,5]))

    def test_template_only_ignores_extra_eq_predictions(self):
        from device_neural_speculation import compile_frame,frame_payload
        eq=dict(kind='eq',name='E')
        rule=dict(slots=[dict(sort=eq,definition='query')]*4,effects=[],query=[
            dict(call=dict(table='F'),args=[dict(slot=i) for i in (0,1)]),
            dict(call=dict(table='F'),args=[dict(slot=i) for i in (2,3)])])
        plan=compile_frame(rule,4,4,dict(tables=[dict(name='F',kind='constructor')]),local_conditions=True)
        state=dict(slots=mx.array([[0,1,0,3]]),slot_roots=mx.array([[0,1,0,3]]),
            slot_valid=mx.ones((1,4),mx.bool_),scalar_numbers=mx.zeros((1,4)),scalar_numeric=mx.zeros((1,4),mx.bool_),
            scalar_codes=mx.zeros((1,4,64)),scalar_valid=mx.zeros((1,4),mx.bool_))
        batch=dict(binding_sources=mx.zeros((1,4),mx.int32),binding_slots=mx.array([[0,1,2,3]]))
        _,roots,ready=frame_payload(state,plan,batch,0,mx.ones(6),mx.array(4),mx.arange(12),mx,template_effects=True,template_only=True)
        self.assertTrue(bool(ready));self.assertEqual(int(roots[3]),1)
        self.assertNotEqual(int(roots[0]),int(roots[1]))


if __name__=='__main__':unittest.main()

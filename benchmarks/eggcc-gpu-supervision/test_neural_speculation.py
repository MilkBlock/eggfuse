import unittest
import numpy as np
import mlx.core as mx
from device_neural_speculation import compile_frame,frame_payload,resolve


class Speculation(unittest.TestCase):
    def test_predicted_eq_changes_roots_without_mutating_base(self):
        eq=dict(kind='eq',name='E');rule=dict(slots=[dict(sort=eq,definition='query')]*2,effects=[dict(kind='union',args=[dict(slot=0),dict(slot=1)])])
        plan=compile_frame(rule,2,2)
        state=dict(slots=mx.array([[0,1]]),slot_roots=mx.array([[0,1]]),slot_valid=mx.ones((1,2),mx.bool_),scalar_numbers=mx.zeros((1,2)),scalar_numeric=mx.zeros((1,2),mx.bool_),scalar_codes=mx.zeros((1,2,64)),scalar_valid=mx.zeros((1,2),mx.bool_))
        batch=dict(binding_sources=mx.array([[0,0]]),binding_slots=mx.array([[0,1]]))
        _,yes,ready=frame_payload(state,plan,batch,0,mx.array([1.]),mx.array(2),mx.arange(8),mx)
        _,no,_=frame_payload(state,plan,batch,0,mx.array([-1.]),mx.array(2),mx.arange(8),mx)
        self.assertTrue(bool(ready));self.assertEqual(int(yes[1]),0);self.assertEqual(int(no[1]),1)
        np.testing.assert_array_equal(state['slot_roots'],[[0,1]])
        _,_,finite=frame_payload(state,plan,batch,0,mx.array([float('nan')]),mx.array(2),mx.arange(8),mx)
        self.assertFalse(bool(finite))
        _,_,bad=frame_payload(state,plan,batch,0,mx.array([1.]),mx.array(-1),mx.arange(8),mx)
        self.assertFalse(bool(bad))

    def test_literal_view_input_keeps_exact_identity_and_unknown_is_rejected(self):
        from device_literal_namespace import bind_effect_literals
        eq=dict(kind='eq',name='E');i64=dict(kind='i64',name='i64')
        literal=dict(literal=(1<<53)+1,sort=i64)
        rule=dict(slots=[dict(sort=i64,definition='query'),dict(sort=eq,definition=0)],
                  effects=[dict(kind='construct',call=dict(table='F'),args=[literal],dst=1,sort=eq)])
        recipe,ids=bind_effect_literals(dict(rules=[rule]),{})
        plan=compile_frame(rule,2,2,recipe)
        state=dict(slots=mx.array([[7,7]]),slot_roots=mx.array([[7,7]]),slot_valid=mx.ones((1,2),mx.bool_),scalar_numbers=mx.zeros((1,2)),scalar_numeric=mx.zeros((1,2),mx.bool_),scalar_codes=mx.zeros((1,2,64)),scalar_valid=mx.zeros((1,2),mx.bool_))
        batch=dict(binding_sources=mx.array([[0]]),binding_slots=mx.array([[-1]]),binding_roots=mx.array([[0]]))
        payload,_,ready=frame_payload(state,plan,batch,0,mx.array([-1.]),mx.array(2),mx.arange(8),mx)
        self.assertTrue(bool(ready));self.assertEqual(int(payload['slots'][0,0]),0)
        self.assertEqual(int(payload['slots'][0,1]),3)
        self.assertTrue(bool(payload['scalar_valid'][0,0]))
        bad=dict(batch,binding_roots=mx.array([[6]]))
        _,_,ready=frame_payload(state,plan,bad,0,mx.array([-1.]),mx.array(2),mx.arange(8),mx)
        self.assertFalse(bool(ready))
        with self.assertRaises(ValueError):compile_frame(rule,2,2,{})

    def test_fresh_handle_reinitialized_after_prior_frame_collapsed_unused_capacity(self):
        eq=dict(kind='eq',name='E')
        rule=dict(slots=[dict(sort=eq,definition='query'),dict(sort=eq,definition=0)],
                  effects=[dict(kind='construct',call=dict(table='F'),args=[dict(slot=0)],dst=1,sort=eq)])
        plan=compile_frame(rule,2,2)
        state=dict(slots=mx.array([[1,2]]),slot_roots=mx.array([[1,2]]),slot_valid=mx.ones((1,2),mx.bool_),scalar_numbers=mx.zeros((1,2)),scalar_numeric=mx.zeros((1,2),mx.bool_),scalar_codes=mx.zeros((1,2,64)),scalar_valid=mx.zeros((1,2),mx.bool_))
        batch=dict(binding_sources=mx.array([[0]]),binding_slots=mx.array([[0]]))
        old=mx.array([0,1,2,0,0,0,0,0])
        payload,roots,ready=frame_payload(state,plan,batch,0,mx.array([-1.]),mx.array(4),old,mx)
        self.assertTrue(bool(ready));self.assertEqual(int(roots[5]),5)
        self.assertEqual(int(payload['slot_roots'][0,1]),5)
        np.testing.assert_array_equal(roots[:4],old[:4])
        np.testing.assert_array_equal(old,[0,1,2,0,0,0,0,0])
        _,merged,_=frame_payload(state,plan,batch,0,mx.array([1.]),mx.array(4),old,mx)
        self.assertEqual(int(merged[5]),1)

    def test_original_set_is_a_constructor_fact_in_cpu_audit(self):
        from reference_cell_closure import facts_from_cells
        rule=dict(query=[dict(call=dict(table='F'),args=[dict(slot=0),dict(slot=1)])],effects=[dict(kind='set',call=dict(table='G'),args=[dict(slot=0)],value=dict(slot=1))])
        state=dict(present=np.array([True]),visible=np.array([True]),settled=np.array([True]),keys=np.array([[0]]),slots=np.array([[0,1]]),slot_valid=np.ones((1,2),bool),effect_pc=np.array([1]))
        facts,ok=facts_from_cells(dict(rules=[rule]),state)
        self.assertTrue(ok);self.assertEqual(set(facts),{('F',(0,),1),('G',(0,),1)})

    def test_stale_audit_cannot_replace_newer_fork_and_rejection_rolls_back(self):
        current=dict(value=mx.array([7,7]));predicted=dict(value=mx.array([0,0]));corrected=dict(value=mx.array([0,1]))
        stale,marks=resolve(current,predicted,corrected,mx.array(False),mx.array(2),mx.array(3),mx)
        np.testing.assert_array_equal(stale['value'],current['value']);self.assertTrue(bool(marks['stale_audit']))
        result,marks=resolve(current,predicted,corrected,mx.array(False),mx.array(3),mx.array(3),mx)
        np.testing.assert_array_equal(result['value'],corrected['value']);self.assertTrue(bool(marks['rolled_back']))


if __name__=='__main__':unittest.main()

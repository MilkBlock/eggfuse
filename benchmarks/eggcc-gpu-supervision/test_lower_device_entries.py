import copy
import unittest
import numpy as np
import mlx.core as mx
from cell_token_successors import compile_catalog
from lower_device_entries import lower, tensors
from device_token_commit import closed_entry_proposals, commit


def recipe(foreign=False,effect=False):
    sort=dict(kind='eq',name='E')
    def slots(n,inputs):return [dict(sort=sort,definition='query' if i<inputs else 'effect') for i in range(n)]
    def atom(name,*args):return dict(call=dict(table=name),args=[dict(slot=s) for s in args])
    source=dict(metadata=dict(source_set='s'),slots=slots(3,2),query=[atom('F',0,1)],
        effects=[dict(kind='construct',call=dict(table='G' if foreign else 'F'),args=[dict(slot=0)],dst=2)])
    consumer=dict(metadata=dict(source_set='s'),slots=slots(2,2),query=[atom('G' if foreign else 'F',0,1)],effects=[])
    if effect:consumer['effects']=[dict(kind='union',args=[dict(slot=0),dict(slot=1)])]
    return dict(tables=[dict(name=n,kind='constructor') for n in ('F','G')],rules=[source,consumer])


class LowerEntries(unittest.TestCase):
    def test_actual_returned_result_not_invented(self):
        r=recipe(True);layout=lower(r,compile_catalog(r))
        self.assertEqual(len(layout['entries']),0)
        self.assertIn('actual_result_witness',layout['marks'][0]['reasons'])
        with self.assertRaisesRegex(ValueError,'no lowered'):tensors(layout,[],[])

    def test_gpu_reads_actual_foreign_result_and_marks_missing_slot(self):
        if not mx.metal.is_available():self.skipTest('Metal required')
        r=recipe(True);layout=lower(r,compile_catalog(r),source_slots=True)
        self.assertEqual(len(layout['entries']),1)
        plan=tensors(layout,np.array([np.eye(3)],np.float32),np.zeros((1,3),np.float32))
        dp={k:mx.array(v) for k,v in plan.items()}
        def execute(result,available):
            state=dict(keys=mx.array([[0,41,72],[-1,-1,-1]],mx.int32),tokens=mx.ones((2,3)),
                slots=mx.array([[41,72,result],[-1,-1,-1]],mx.int32),slot_valid=mx.array([[True,True,available],[False,False,False]]),
                present=mx.array([True,False]),active=mx.array([True,False]),visible=mx.array([True,False]),
                settled=mx.array([True,False]),readers=mx.array([False,False]),generation=mx.array([1,0],mx.int32))
            out,m=mx.compile(lambda s:commit(s,closed_entry_proposals(s,dp,mx.array(0),mx),mx))(state)
            mx.eval(out,m);return out,m
        out,m=execute(999,True)
        np.testing.assert_array_equal(np.array(out['keys'])[1],[1,41,999])
        np.testing.assert_array_equal(np.array(out['slots'])[1],[41,999,-1])
        out,m=execute(1234,True)
        self.assertEqual(int(np.array(out['keys'])[1,2]),1234)
        out,m=execute(999,False)
        self.assertEqual(int(np.array(out['present']).sum()),1)
        self.assertTrue(bool(np.array(m['needs_attention'])))
        self.assertTrue(np.array(m['missing_witness']).any())

    def test_stage_boundary_and_corrupt_contract(self):
        r=recipe();r['rules'][1]['metadata']['source_set']='later'
        catalog=compile_catalog(r);layout=lower(r,catalog)
        self.assertEqual(len(layout['entries']),0)
        self.assertIn('source_run_boundary',layout['marks'][0]['reasons'])
        catalog['edges'][0]['contract']['completed_effect_prefix']=0
        with self.assertRaisesRegex(ValueError,'contract mismatch'):lower(r,catalog)

    def run_gpu(self,effect):
        r=recipe(effect=effect);layout=lower(r,compile_catalog(r))
        self.assertEqual(len(layout['entries']),1)
        plan=tensors(layout,np.array([np.eye(3)],np.float32),np.zeros((1,3),np.float32))
        state=dict(keys=np.array([[0,41,72],[-1,-1,-1]],np.int32),tokens=np.array([[.2,.3,.4],[0,0,0]],np.float32),
            present=np.array([True,False]),active=np.array([True,False]),visible=np.array([True,False]),
            settled=np.array([True,False]),readers=np.array([False,False]),generation=np.array([1,0],np.int32))
        dp={k:mx.array(v) for k,v in plan.items()}
        def run(s):
            s,first=commit(s,closed_entry_proposals(s,dp,mx.array(0),mx),mx)
            s,second=commit(s,closed_entry_proposals(s,dp,mx.array(0),mx),mx)
            return s,first,second
        out,a,b=mx.compile(run)({k:mx.array(v) for k,v in state.items()});mx.eval(out,a,b)
        np.testing.assert_array_equal(np.array(out['keys'])[1],[1,41,72])
        self.assertEqual(int(np.array(a['accepted']).sum()),1)
        self.assertEqual(int(np.array(b['accepted']).sum()),0)
        self.assertFalse(np.array(a['transferred']).any())
        self.assertTrue(np.array(out['active'])[0])
        return out,b

    def test_compiled_query_projection_executes_on_gpu(self):
        if not mx.metal.is_available():self.skipTest('Metal required')
        mx.set_default_device(mx.gpu);out,marks=self.run_gpu(False)
        self.assertTrue(np.array(out['settled'])[1]);self.assertFalse(bool(np.array(marks['needs_attention'])))

    def test_query_hit_does_not_complete_union_or_authorize_stop(self):
        if not mx.metal.is_available():self.skipTest('Metal required')
        mx.set_default_device(mx.gpu);out,marks=self.run_gpu(True)
        self.assertFalse(np.array(out['settled'])[1]);self.assertTrue(bool(np.array(marks['needs_attention'])))
        self.assertTrue(bool(np.array(marks['no_new_admission'])))


if __name__=='__main__':unittest.main()

import copy
import unittest
import numpy as np
import mlx.core as mx
from cell_token_successors import compile_catalog
from context_effect_projection import compile_context
from device_alias_completion import compile_rule
from lower_device_entries import lower,tensors
from device_token_commit import closed_entry_proposals,commit


def recipe():
    def slots(n):return [dict(sort=dict(kind='eq',name='E'),definition='query' if i<2 else 'effect') for i in range(n)]
    query=[dict(call=dict(table='G'),args=[dict(slot=0),dict(slot=1)])]
    def construct(t,a,d):return dict(kind='construct',call=dict(table=t),args=[dict(slot=a)],dst=d)
    return dict(tables=[dict(name=t,kind='constructor') for t in ('G','F')],rules=[
        dict(metadata=dict(source_set='s'),slots=slots(4),query=query,effects=[construct('G',0,2),construct('F',1,3)]),
        dict(metadata=dict(source_set='s'),slots=slots(3),query=query,effects=[construct('F',1,2)])])


class ContextEffects(unittest.TestCase):
    def test_producer_supplies_fact_absent_from_consumer_query(self):
        r=recipe();catalog=compile_catalog(r);edge=catalog['edges'][0]
        self.assertFalse(compile_rule(r['rules'][1],{t['name']:t for t in r['tables']})['covered'])
        p=compile_context(r,edge)
        self.assertTrue(p['covered']);self.assertEqual(p['projection'][2],3)
        self.assertEqual(p['reused_constructors'],1)
        self.assertFalse(p['ownership_transfer_authorized'])

    def test_new_union_is_not_proved_by_future_effect(self):
        r=recipe();r['rules'][1]['effects'].append(dict(kind='union',args=[dict(slot=2),dict(slot=0)]))
        p=compile_context(r,compile_catalog(r)['edges'][0])
        self.assertFalse(p['covered']);self.assertEqual(p['reason'],'new_equality')

    def test_overwritten_source_result_is_rejected(self):
        r=recipe();r['rules'][0]['effects'].append(dict(kind='copy',dst=3,arg=dict(slot=0)))
        p=compile_context(r,compile_catalog(r)['edges'][0])
        self.assertFalse(p['covered']);self.assertEqual(p['reason'],'overwritten_source_result')

    def test_context_completed_token_is_created_on_gpu(self):
        if not mx.metal.is_available():self.skipTest('Metal required')
        mx.set_default_device(mx.gpu)
        r=recipe();layout=lower(r,compile_catalog(r),source_slots=True,context_completion=True)
        self.assertEqual(len(layout['entries']),1)
        p=tensors(layout,np.array([np.eye(3)],np.float32),np.zeros((1,3),np.float32));plan={k:mx.array(v) for k,v in p.items()}
        def run(available):
            state=dict(keys=mx.array([[0,41,72],[-1,-1,-1]],mx.int32),tokens=mx.array([[.2,.3,.4],[0.,0.,0.]]),
                slots=mx.array([[41,72,72,999],[-1,-1,-1,-1]],mx.int32),slot_roots=mx.array([[41,72,72,11],[-1,-1,-1,-1]],mx.int32),slot_valid=mx.array([[True,True,True,available],[False]*4]),
                present=mx.array([True,False]),active=mx.array([True,False]),visible=mx.array([True,False]),
                settled=mx.array([True,False]),readers=mx.array([False,False]),generation=mx.array([1,0],mx.int32))
            out,m=mx.compile(lambda s:commit(s,closed_entry_proposals(s,plan,mx.array(0),mx),mx))(state)
            mx.eval(out,m);return out,m
        out,m=run(True)
        np.testing.assert_array_equal(np.array(out['slots'])[1],[41,72,999,-1])
        np.testing.assert_array_equal(np.array(out['slot_roots'])[1],[41,72,11,-1])
        self.assertTrue(np.array(out['settled'])[1]);self.assertFalse(np.array(m['transferred']).any())
        out,m=run(False)
        self.assertEqual(np.array(out['present']).sum(),1)
        self.assertTrue(np.array(m['missing_witness']).any())


if __name__=='__main__':unittest.main()

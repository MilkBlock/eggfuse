import unittest
import numpy as np
import mlx.core as mx
from device_stage_models import membership,compile_bank,select,compile_program
from device_schedule import compile_schedule
from device_scheduled_runtime import run
from test_device_scheduled_runtime import fixture
from cell_token_successors import compile_catalog
from lower_device_entries import lower,tensors
from device_token_commit import closed_entry_proposals
import test_device_constructor_completion as helper


class StageModels(unittest.TestCase):
    def test_composed_membership_not_source_annotation_controls_entry(self):
        recipe=helper.recipe()
        recipe['rulesets']=[dict(name='combined',rule_ids=list(range(len(recipe['rules'])))),dict(name='other',rule_ids=[]),dict(name='also',rule_ids=list(range(len(recipe['rules']))))]
        names,matrix,authority=membership(recipe);self.assertTrue(authority)
        self.assertEqual(names,['combined','other','also']);self.assertTrue(matrix[:,0].all());self.assertFalse(matrix[:,1].any())
        layout=lower(recipe,compile_catalog(recipe),source_slots=True)
        self.assertEqual(layout['stages'],names)
        s,_,_,_,_,_,_=fixture()
        e=layout['entries'][0];p=tensors(dict(layout,entries=[e]),np.zeros((1,128,128)),np.zeros((1,128)))
        a=closed_entry_proposals(s,p,0,np,token_values=np.zeros_like(s['tokens']))
        b=closed_entry_proposals(s,p,2,np,token_values=np.zeros_like(s['tokens']))
        off=closed_entry_proposals(s,p,1,np,token_values=np.zeros_like(s['tokens']))
        np.testing.assert_array_equal(a['matched'],b['matched']);self.assertTrue(a['matched'].any());self.assertFalse(off['matched'].any())

    def test_compiler_shares_authoritative_stage_order(self):
        recipe=dict(rules=[dict(metadata=dict(source_set='unrelated'))],rulesets=[dict(name='b',rule_ids=[0]),dict(name='a',rule_ids=[0])],control=dict(run='b'))
        schedule,bank,meta=compile_program(recipe,{'a':dict(w=np.ones(2)),'b':dict(w=np.full(2,7.))})
        self.assertEqual(meta['stages'],['b','a'])
        chosen,ready=select(bank,schedule['stage'][0],np)
        self.assertTrue(ready);np.testing.assert_array_equal(chosen['w'],[7.,7.])

    def test_device_bank_selects_once_for_batch_and_rejects_uncovered_stage(self):
        bank=compile_bank(['a','b','missing'],{'a':dict(w=np.ones((3,4))), 'b':dict(w=np.full((3,4),7.))})
        device=dict(parameters={k:mx.array(v) for k,v in bank['parameters'].items()},available=mx.array(bank['available']))
        for stage,want in ((0,1),(1,7)):
            m,ready=mx.compile(lambda x:select(device,x,mx))(mx.array(stage));mx.eval(m,ready)
            self.assertTrue(bool(ready));np.testing.assert_array_equal(m['w'],np.full((3,4),want))
        for stage in (-1,2,3):self.assertFalse(bool(select(device,mx.array(stage),mx)[1]))
        with self.assertRaises(ValueError):compile_bank(['a','b'],{'a':dict(w=np.ones(2)),'b':dict(w=np.ones(3))})

    def test_scheduled_execution_uses_distinct_stage_weights_without_refresh(self):
        from device_entry_round import run_round
        s,n,b,m,p,_,_=fixture()
        c,meta=compile_schedule(dict(sequence=[dict(run='a'),dict(run='b')]),['a','b'])
        bank=compile_bank(['a','b'],{'a':m,'b':{k:v*2 for k,v in m.items()}})
        b=[(dict(plan,stage=np.array([0 if int(plan['producer'][0])==0 else 1],np.int32)),inputs,coefficients) for plan,inputs,coefficients in b]
        seen=[]
        def query(state,blocks,model,stage,xp,**kw):
            # Capture device-selected weights, not host inspection of stage.
            seen.append((stage,model['w'][0,0]))
            return run_round(state,blocks,model,stage,xp,key_context=kw.get('key_context'))
        dev=lambda d:{k:mx.array(v) for k,v in d.items()}
        db=[tuple(dev(v) for v in block) for block in b]
        bank=dict(parameters=dev(bank['parameters']),available=mx.array(bank['available']))
        def execute():
            out,last,marks=run(dev(s),db,dev(m),helper.device_plan(p),dev(c),meta['repeat_slots'],mx.array([True,True]),mx.array(n),mx.array(200),mx.array(100),mx.array(True),mx.array(True),5,mx,query_kernel=query,stage_models=bank)
            return out,last,marks,mx.stack([mx.stack([stage.astype(mx.float32),v]) for stage,v in seen])
        out,last,marks,trace=mx.compile(execute)();mx.eval(out,last,marks,trace)
        self.assertTrue(bool(marks['finished']));self.assertFalse(bool(mx.any(marks['missing_stage_model'])))
        active=[(int(stage),float(v)) for stage,v in np.array(trace) if int(stage)>=0]
        self.assertEqual([x[0] for x in active],[0,1]);self.assertAlmostEqual(active[1][1],2*active[0][1])
        np.testing.assert_array_equal(np.array(out['tokens'])[s['present']],s['tokens'][s['present']])
        self.assertEqual(int(mx.sum(out['present'])),3)
        np.testing.assert_array_equal(np.array(marks['new_tokens'])[:2],[1,1])
        np.testing.assert_array_equal(np.array(out['keys'])[2],[2,100,101])
        first,_,_=run(dev(s),db,dev(m),helper.device_plan(p),dev(c),meta['repeat_slots'],mx.array([True,True]),mx.array(n),mx.array(200),mx.array(100),mx.array(True),mx.array(True),1,mx,stage_models=bank)
        np.testing.assert_array_equal(out['tokens'][1],first['tokens'][1])

    def test_missing_model_blocks_effects_and_stage_advance(self):
        s,n,b,m,p,c,meta=fixture();bank=compile_bank(['s','unused'],{'unused':m})
        out,last,marks=run(s,b,m,p,c,meta['repeat_slots'],np.array([True,True]),n,np.array(200),np.array(100),np.array(True),np.array(True),6,np,stage_models=bank)
        self.assertFalse(marks['finished']);self.assertTrue(marks['failed_run']);self.assertTrue(marks['missing_stage_model'].any())
        self.assertEqual(last,n);self.assertEqual(marks['new_tokens'].sum(),0);self.assertEqual(marks['run_done'].sum(),0)
        for k in s:np.testing.assert_array_equal(out[k],s[k])


if __name__=='__main__':unittest.main()

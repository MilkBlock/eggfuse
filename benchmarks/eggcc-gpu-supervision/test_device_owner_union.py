import unittest
import numpy as np
import mlx.core as mx
from device_slot_owners import pack,read,compile_transfer,transfer
from device_eq_completion import refresh_slots


class OwnerUnion(unittest.TestCase):
    def test_ordered_completion_refreshes_every_shared_alias(self):
        from test_device_ordered_union import fixture,device_plan
        from device_constructor_completion import complete
        state,plan,context=fixture()
        for key,value in list(state.items()):state[key]=np.concatenate([value,value[1:]],axis=0)
        state=pack(state);state['slot_owner'][2]=1;state['owner_live'][2]=False
        dp=device_plan(plan);dc={k:mx.array(v) for k,v in context.items()}
        out,n,m=mx.compile(lambda s:complete(s,dp,mx.array(10),mx.array(16),mx.array(6),mx.array(True),mx.array(True),mx,dc,4))({k:mx.array(v) for k,v in state.items()});mx.eval(out,n,m)
        self.assertTrue(bool(m['eq_settled']));self.assertEqual(int(n),10)
        self.assertEqual(int(m['new_equivalences']),2);self.assertEqual(int(m['refreshed']),3)
        self.assertFalse(np.array(out['token_dirty']).any());self.assertNotIn('slot_roots',out)
        self.assertEqual(int(out['owner_slot_roots'][1,0]),3)
        np.testing.assert_array_equal(np.array(out['owner_slots'])[1],state['owner_slots'][1])
        self.assertEqual(np.array(out['owner_live']).sum(),2)
        np.testing.assert_allclose(np.array(out['tokens'])[1],np.array(out['tokens'])[2],atol=1e-6)

    def test_bad_alias_type_or_generation_cannot_claim_root_refresh_validity(self):
        from test_device_slot_owners import fixture
        _,dense,plan=fixture();s,_=transfer(pack(dense),plan,np.array(0),np.array(1),np.array(2),np.array(5),np.array(True),np)
        for mode in ('type','generation'):
            current={k:v.copy() for k,v in s.items()};eq=np.ones((2,3),bool)
            if mode=='type':eq[1,0]=False
            else:current['owner_epoch'][0]+=1
            out,bad=refresh_slots(current,np.arange(128,dtype=np.int32),eq,np)
            self.assertTrue(bad,mode)
            if mode=='type':np.testing.assert_array_equal(out['owner_slot_roots'],current['owner_slot_roots'])

    def test_budget_and_external_gap_preserve_pending_union(self):
        from test_device_ordered_union import fixture
        from device_constructor_completion import complete
        for rounds,external in ((1,True),(4,False)):
            s,p,c=fixture();out,n,m=complete(pack(s),p,np.array(10),np.array(16),np.array(6),np.array(external),np.array(True),np,c,rounds)
            self.assertEqual(out['effect_pc'][0],0);self.assertEqual(n,10)
            self.assertTrue(m['needs_attention']);self.assertFalse(m['eq_settled'])

    def test_gpu_owner_takeover_union_and_two_ruleset_saturations(self):
        from test_device_join_transition import fixture,device_plan
        import test_device_query_join as qfixture
        from device_join_transition import compile_transition,run_round
        from device_constructor_completion import compile_completion
        from test_device_ordered_union import device_plan as completion_plan
        from device_scheduled_runtime import run
        from device_schedule import compile_schedule
        recipe,_=qfixture.fixture();s,_,model=fixture()
        # Four logical rows, three physical rows; takeover frees a row before admission.
        for key,value in list(s.items()):s[key]=np.concatenate([value,value[2:3]],axis=0)
        for key in ('slots','slot_roots','slot_valid'):
            s[key]=np.concatenate([s[key],np.full((4,1),False if key=='slot_valid' else -1,s[key].dtype)],axis=1)
        recipe['tables'].append(dict(name='H',kind='constructor'))
        recipe['rules'][2]['slots'].append(dict(sort=dict(kind='eq',name='E'),definition='effect'))
        recipe['rules'][2]['effects']=[dict(kind='union',args=[dict(slot=0),dict(slot=1)]),dict(kind='construct',call=dict(table='H'),args=[dict(slot=2)],dst=3)]
        recipe['rules'].append(dict(metadata=dict(source_set='t'),slots=[dict(sort=dict(kind='eq',name='E'),definition='query') for _ in range(2)],query=[dict(call=dict(table='H'),args=[dict(slot=0),dict(slot=1)])],effects=[]))
        cp=completion_plan(compile_completion(recipe,4,include_unions=True))
        blocks=[(0,device_plan(compile_transition(recipe,2))),(1,device_plan(compile_transition(recipe,3)))]
        tp=compile_transfer(recipe,dict(producer=0,consumer=1,projection=[0,0],projection_valid=[False,False]),4)
        tp={k:mx.array(v) if isinstance(v,np.ndarray) else v for k,v in tp.items()}
        packed=pack(s)
        for key in list(packed):
            if key.startswith('owner_') and key not in ('owner_epoch','owner_projection'):packed[key]=packed[key][:3]
        schedule,meta=compile_schedule(dict(sequence=[dict(saturate=dict(run='s')),dict(saturate=dict(run='t'))]),['s','t'])
        dev=lambda d:{k:mx.array(v) for k,v in d.items()}
        dm,ds=dev(model),dev(schedule)
        roots=np.arange(256,dtype=np.int32);roots[99]=10;roots[100]=10;roots[200]=20
        ctx=dict(roots=mx.array(roots),sorts=mx.zeros(256,mx.int32))
        def flow(state):
            state,tm=transfer(state,tp,mx.array(0),mx.array(1),state['generation'][0],state['generation'][1],mx.array(True),mx)
            out,n,m=run(state,blocks,dm,cp,ds,meta['repeat_slots'],mx.array([True,True]),mx.array(201),mx.array(256),mx.array(55),mx.array(True),mx.array(True),24,mx,eq_context=ctx,query_kernel=run_round)
            return out,n,m,tm
        out,n,m,tm=mx.compile(flow)(dev(packed));mx.eval(out,n,m,tm)
        self.assertTrue(bool(tm['transferred']));self.assertTrue(bool(m['finished']))
        self.assertEqual(int(n),202);self.assertEqual(np.array(out['present']).sum(),4)
        self.assertEqual(np.array(out['owner_live']).sum(),3)
        done=np.array(m['run_done']);self.assertEqual(np.array(m['run_changed'])[done].tolist(),[True,False,False])
        self.assertEqual(np.array(m['stage'])[done].tolist(),[0,0,1])
        self.assertEqual(np.array(m['new_tokens']).sum(),2)
        self.assertFalse(np.array(out['token_dirty']).any());self.assertNotIn('slots',out)
        final={k:np.array(v) for k,v in out.items()}
        np.testing.assert_array_equal(read(final,'slots',np.array(2),np.arange(4),np),[7,100,200,201])
        np.testing.assert_array_equal(read(final,'slots',np.array(3),np.arange(2),np),[200,201])
        np.testing.assert_array_equal(read(final,'slot_roots',np.array(0),np.arange(2),np),[7,7])
        reference,rn,rm=run(s,[(0,compile_transition(recipe,2)),(1,compile_transition(recipe,3))],model,compile_completion(recipe,4,include_unions=True),schedule,meta['repeat_slots'],np.array([True,True]),np.array(201),np.array(256),np.array(55),np.array(True),np.array(True),24,np,eq_context=dict(roots=roots,sorts=np.zeros(256,np.int32)),query_kernel=run_round)
        self.assertEqual(int(n),rn)
        rows=np.arange(4)[:,None];slots=np.arange(4)[None,:]
        valid=read(final,'slot_valid',rows,slots,np)
        np.testing.assert_array_equal(valid,reference['slot_valid'])
        for column in ('slots','slot_roots'):
            np.testing.assert_array_equal(read(final,column,rows,slots,np)[valid],reference[column][valid])
        for key in ('keys','present','active','visible','settled','effect_pc','generation'):
            np.testing.assert_array_equal(final[key],reference[key])
        np.testing.assert_allclose(final['tokens'],reference['tokens'],atol=3e-6)
        np.testing.assert_array_equal(np.array(m['eq_context']['roots']),rm['eq_context']['roots'])
        for key in ('stage','run_done','run_changed','new_tokens','new_constructors','new_equivalences'):
            np.testing.assert_array_equal(np.array(m[key]),rm[key])


if __name__=='__main__':unittest.main()

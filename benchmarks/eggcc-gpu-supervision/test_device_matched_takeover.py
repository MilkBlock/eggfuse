import unittest
import numpy as np
import mlx.core as mx
from device_matched_takeover import compile_catalog,initialize,finish
from device_slot_owners import pack,read
from device_join_transition import step
from test_device_join_transition import fixture,device_plan
from test_device_query_join import fixture as recipe_fixture


def setup():
    recipe,_=recipe_fixture();s,p,m=fixture();s['readers'][:]=False
    for key in ('slots','slot_roots','slot_valid'):
        s[key]=np.concatenate([s[key],np.full((3,1),False if key=='slot_valid' else -1,s[key].dtype)],axis=1)
    blocks,catalog,atoms=compile_catalog(recipe,[(0,p)],4)
    return initialize(pack(s),atoms),blocks[0][1],catalog,m


class MatchedTakeover(unittest.TestCase):
    def test_budget_preserves_unprocessed_evidence(self):
        s,p,c,m=setup();matched,_=step(s,p,m,4,True,True,np)
        # A stale hint precedes the valid newly admitted consumer.
        for key in ('takeover_plan','takeover_source','takeover_generation'):
            matched[key][1]=matched[key][2]
        matched['takeover_target_generation'][1]=-1
        out,marks=finish(matched,c,np.array(True),np,budget=1)
        self.assertEqual(marks['released'],0)
        self.assertTrue((out['takeover_plan'][1]==-1).all())
        np.testing.assert_array_equal(out['takeover_plan'][2],matched['takeover_plan'][2])
        final,marks=finish(out,c,np.array(True),np,budget=1)
        self.assertEqual(marks['released'],2)
        self.assertTrue((final['takeover_plan']==-1).all())

    def test_run_completion_automatically_reclaims_for_next_ruleset(self):
        from device_join_transition import compile_transition,run_round
        from device_constructor_completion import compile_completion
        from device_scheduled_runtime import run
        from device_schedule import compile_schedule
        from test_device_ordered_union import device_plan as completion_plan
        recipe,_=recipe_fixture();s,_,model=fixture();s['readers'][:]=False
        for key,value in list(s.items()):s[key]=np.concatenate([value,value[2:3]],axis=0)
        for key in ('slots','slot_roots','slot_valid'):
            s[key]=np.concatenate([s[key],np.full((4,2),False if key=='slot_valid' else -1,s[key].dtype)],axis=1)
        recipe['tables'].append(dict(name='H',kind='constructor'))
        recipe['rules'][2]['slots'].append(dict(sort=dict(kind='eq',name='E'),definition='effect'))
        recipe['rules'][2]['effects']=[dict(kind='union',args=[dict(slot=0),dict(slot=1)]),dict(kind='construct',call=dict(table='H'),args=[dict(slot=2)],dst=3)]
        recipe['rules'].append(dict(metadata=dict(source_set='t'),slots=[dict(sort=dict(kind='eq',name='E'),definition='query') for _ in range(2)],query=[dict(call=dict(table='H'),args=[dict(slot=0),dict(slot=1)])],effects=[]))
        blocks,catalog,atoms=compile_catalog(recipe,[(0,compile_transition(recipe,2)),(1,compile_transition(recipe,3))],5)
        packed=initialize(pack(s),atoms)
        for key in list(packed):
            if key.startswith('owner_') and key not in ('owner_epoch','owner_projection'):packed[key]=packed[key][:3]
        schedule,meta=compile_schedule(dict(sequence=[dict(saturate=dict(run='s')),dict(saturate=dict(run='t'))]),['s','t'])
        cp=compile_completion(recipe,5,include_unions=True)
        roots=np.arange(256,dtype=np.int32);roots[99]=10;roots[100]=10;roots[200]=20
        context=dict(roots=roots,sorts=np.zeros(256,np.int32))
        dev=lambda d:{k:mx.array(v) for k,v in d.items()}
        db=[(stage,device_plan(plan)) for stage,plan in blocks];dc=completion_plan(cp)
        ds,dm,ctx=dev(schedule),dev(model),dev(context)
        def flow(state,capture=False):
            def query(s,b,m,stage,xp,**kwargs):return run_round(s,b,m,stage,xp,capture=capture,**kwargs)
            return run(state,db,dm,dc,ds,meta['repeat_slots'],mx.array([True,True]),mx.array(201),mx.array(256),mx.array(55),mx.array(True),mx.array(True),12,mx,eq_context=ctx,query_kernel=query,takeover_catalog=catalog)
        out,n,marks=mx.compile(flow)(dev(packed));mx.eval(out,n,marks)
        self.assertTrue(bool(marks['finished']));self.assertEqual(int(n),202)
        self.assertEqual(int(mx.sum(marks['takeover_released'])),2)
        self.assertEqual(int(mx.sum(out['owner_live'])),2)
        self.assertEqual(int(mx.sum(marks['new_tokens'])),2)
        done=np.array(marks['run_done']);self.assertEqual(np.array(marks['stage'])[done].tolist(),[0,0,1])
        # Observation must not disable transfer or alter later-stage queries.
        captured,cn,cm=mx.compile(lambda state:flow(state,True))(dev(packed));mx.eval(captured,cn,cm)
        self.assertEqual(int(cn),int(n))
        for key in out:
            if np.issubdtype(np.array(out[key]).dtype,np.floating):np.testing.assert_allclose(np.array(captured[key]),np.array(out[key]),atol=3e-6)
            else:np.testing.assert_array_equal(np.array(captured[key]),np.array(out[key]))
        for key in ('stage','run_done','new_tokens','takeover_released','takeover_blocked'):
            np.testing.assert_array_equal(np.array(cm[key]),np.array(marks[key]))
        from device_match_capture import audit
        recorded=[c for tick in cm['query_captures'] for c in tick if bool(c['recorded'])]
        self.assertTrue(recorded)
        for c in recorded:self.assertTrue(audit(recipe,c)['passed'])
        # Dense execution has no capacity pressure and provides the same semantics.
        ref,rn,rm=run(s,blocks,model,cp,schedule,meta['repeat_slots'],np.array([True,True]),np.array(201),np.array(256),np.array(55),np.array(True),np.array(True),12,np,eq_context=context,query_kernel=run_round)
        final={k:np.array(v) for k,v in out.items()};rows=np.arange(4)[:,None];slots=np.arange(5)[None,:]
        valid=read(final,'slot_valid',rows,slots,np)
        np.testing.assert_array_equal(valid,ref['slot_valid'])
        for key in ('slots','slot_roots'):np.testing.assert_array_equal(read(final,key,rows,slots,np)[valid],ref[key][valid])
        np.testing.assert_allclose(final['tokens'],ref['tokens'],atol=3e-6)
        for key in ('keys','generation','present','active','visible','effect_pc','settled'):np.testing.assert_array_equal(final[key],ref[key])
        for key in ('stage','run_done','run_changed','new_tokens'):np.testing.assert_array_equal(np.array(marks[key]),rm[key])

    def test_actual_multi_source_matches_release_both_payloads_on_gpu(self):
        s,p,c,m=setup();dp=device_plan(p);dm={k:mx.array(v) for k,v in m.items()}
        def flow(state):
            matched,marks=step(state,dp,dm,4,mx.array(True),mx.array(True),mx)
            out,tm=finish(matched,c,mx.array(True),mx)
            return out,marks,tm
        out,marks,tm=mx.compile(flow)({k:mx.array(v) for k,v in s.items()});mx.eval(out,marks,tm)
        final={k:np.array(v) for k,v in out.items()}
        self.assertEqual(int(tm['released']),2);self.assertEqual(int(tm['copied_fields']),1)
        self.assertEqual(final['owner_live'].sum(),1);self.assertEqual(final['present'].sum(),3)
        self.assertTrue((final['takeover_plan']==-1).all())
        np.testing.assert_array_equal(read(final,'slots',np.array(0),np.arange(2),np),[7,100])
        np.testing.assert_array_equal(read(final,'slots',np.array(1),np.arange(2),np),[99,200])
        np.testing.assert_array_equal(read(final,'slots',np.array(2),np.arange(3),np),[7,100,200])
        before,_=step(s,p,m,4,True,True,np)
        for key in ('keys','tokens','present','visible','active','generation'):
            np.testing.assert_allclose(final[key],before[key],atol=2e-6)

    def test_evidence_waits_for_boundary_and_readers_and_rejects_stale_source(self):
        s,p,c,m=setup();matched,_=step(s,p,m,4,True,True,np)
        for boundary,reader in ((False,False),(True,True)):
            pending={k:v.copy() for k,v in matched.items()};pending['readers'][0]=reader
            out,tm=finish(pending,c,np.array(boundary),np)
            self.assertEqual(tm['released'],0)
            np.testing.assert_array_equal(out['takeover_plan'],pending['takeover_plan'])
        matched['generation'][:2]+=1
        out,tm=finish(matched,c,np.array(True),np)
        self.assertEqual(tm['released'],0);self.assertEqual(tm['blocked'],2)
        np.testing.assert_array_equal(out['owner_live'],matched['owner_live'])
        matched,_=step(s,p,m,4,True,True,np);matched['generation'][2]+=1
        out,tm=finish(matched,c,np.array(True),np)
        self.assertEqual(tm['released'],0);self.assertEqual(tm['blocked'],2)

    def test_duplicate_matches_do_not_replace_retained_evidence(self):
        s,p,c,m=setup();matched,_=step(s,p,m,4,True,True,np)
        again,marks=step(matched,p,m,4,True,True,np)
        self.assertFalse(marks['admission']['accepted'].any())
        for key in ('takeover_plan','takeover_source','takeover_generation'):
            np.testing.assert_array_equal(again[key],matched[key])

if __name__=='__main__':unittest.main()

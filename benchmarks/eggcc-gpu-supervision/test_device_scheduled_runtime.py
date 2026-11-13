import unittest
import numpy as np
import mlx.core as mx
import test_device_constructor_completion as helper
from cell_token_successors import compile_catalog
from lower_device_entries import lower,tensors
from device_constructor_completion import compile_completion,complete
from device_entry_transition import compile_features
from device_schedule import compile_schedule
from device_scheduled_runtime import run


def fixture():
    recipe=helper.recipe();cp=compile_completion(recipe,3)
    state,next_id,_=complete(helper.state(),cp,np.array(100),np.array(200),np.array(100),np.array(True),np.array(True),np)
    lowered=lower(recipe,compile_catalog(recipe),source_slots=True);blocks=[]
    for e in lowered['entries']:
        p=tensors(dict(lowered,entries=[e]),np.zeros((1,128,128)),np.zeros((1,128)));p.pop('weights');p.pop('bias')
        il,cl=compile_features(recipe,e);blocks.append((p,il,cl))
    rng=np.random.default_rng(73);model=dict(w=rng.normal(0,.01,(1408,16)).astype(np.float32),coef=rng.normal(0,.01,(1425,128)).astype(np.float32))
    schedule,meta=compile_schedule(dict(saturate=dict(run='s')),['s'])
    return state,next_id,blocks,model,cp,schedule,meta


class ScheduledRuntime(unittest.TestCase):
    def test_real_effects_drive_saturation_not_new_token_count(self):
        if not mx.metal.is_available():self.skipTest('Metal required')
        s,n,b,m,p,c,meta=fixture();dev=lambda d:{k:mx.array(v) for k,v in d.items()}
        db=[tuple(dev(v) for v in block) for block in b];dm=dev(m);dp=helper.device_plan(p);dc=dev(c)
        out,n,marks=mx.compile(lambda state:run(state,db,dm,dp,dc,meta['repeat_slots'],mx.array([True]),mx.array(n),mx.array(200),mx.array(100),mx.array(True),mx.array(True),12,mx))(dev(s));mx.eval(out,n,marks)
        done=np.array(marks['run_done']);self.assertEqual(done.sum(),2)
        self.assertEqual(np.array(marks['run_changed'])[done].tolist(),[True,False])
        self.assertEqual(np.array(marks['new_tokens'])[done].tolist(),[1,1])
        self.assertEqual(np.array(marks['new_constructors']).sum(),1)
        self.assertTrue(bool(marks['finished']));self.assertEqual(int(n),102)

    def test_waiting_run_does_not_rematch_and_resumes_same_snapshot(self):
        s,n,b,m,p,c,meta=fixture()
        out,n,first=run(s,b,m,p,c,meta['repeat_slots'],np.array([True]),n,np.array(200),np.array(100),np.array(False),np.array(True),6,np)
        self.assertEqual(first['query_started'].sum(),1);self.assertFalse(first['finished']);self.assertTrue(first['open_run'])
        out,n,last=run(out,b,m,p,c,meta['repeat_slots'],np.array([True]),n,np.array(200),np.array(100),np.array(True),np.array(True),12,np,continuation=first)
        self.assertEqual(last['query_started'].sum(),1);self.assertTrue(last['finished']);self.assertEqual(n,102)
        self.assertEqual(last['run_done'].sum(),2)

    def test_uncovered_query_holds_program_counter_after_effects_finish(self):
        s,n,b,m,p,c,meta=fixture()
        out,n,marks=run(s,b,m,p,c,meta['repeat_slots'],np.array([False]),n,np.array(200),np.array(100),np.array(True),np.array(True),8,np)
        self.assertFalse(marks['finished']);self.assertEqual(marks['query_started'].sum(),1)
        self.assertEqual(marks['run_done'].sum(),0);self.assertTrue(marks['unreported_change'])


if __name__=='__main__':unittest.main()

import unittest
import numpy as np
import mlx.core as mx
import test_device_query_join as query_fixture
from device_join_transition import compile_transition,step,proposals
from device_token_commit import commit


def fixture():
    recipe,state=query_fixture.fixture();state['keys']=np.array([[0,7,100,-1],[1,99,200,-1]],np.int32)
    for key,value in list(state.items()):state[key]=np.concatenate([value,np.zeros((1,)+value.shape[1:],value.dtype)],axis=0)
    state['keys'][2]=-1;state['slots'][2]=-1;state['slot_roots'][2]=-1
    state['active']=np.array([False,False,False]);state['readers']=np.array([True,True,False]);state['token_dirty']=np.zeros(3,bool)
    rng=np.random.default_rng(93);state['tokens']=rng.normal(0,.1,(3,128)).astype(np.float32)
    model=dict(w=rng.normal(0,.01,(1408,16)).astype(np.float32),coef=rng.normal(0,.01,(1425,128)).astype(np.float32))
    return state,compile_transition(recipe,2),model


def device_plan(p):
    dev=lambda d:{k:mx.array(v) for k,v in d.items()}
    return dict(p,query=query_fixture.device_plan(p['query']),inputs=dev(p['inputs']),
                ports=[dict(port,edge=mx.array(port['edge']),route=mx.array(port['route'])) for port in p['ports']])


class JoinTransition(unittest.TestCase):
    def test_multi_source_query_ridge_and_admission_on_gpu(self):
        if not mx.metal.is_available():self.skipTest('Metal required')
        s,p,m=fixture();dp=device_plan(p);dm={k:mx.array(v) for k,v in m.items()};ds={k:mx.array(v) for k,v in s.items()}
        out,marks=mx.compile(lambda state:step(state,dp,dm,4,mx.array(True),mx.array(True),mx))(ds);mx.eval(out,marks)
        self.assertTrue(bool(marks['query_complete']));self.assertEqual(np.array(marks['admission']['accepted']).sum(),1)
        np.testing.assert_array_equal(np.array(out['keys'])[2],[2,7,100,200])
        np.testing.assert_array_equal(np.array(out['slot_roots'])[2],[7,10,20])
        self.assertTrue(np.array(out['present']).all());self.assertFalse(np.array(marks['admission']['transferred']).any())
        self.assertFalse(np.array(out['active'])[:2].any()) # shared readers need not own activation
        expected,_=step(s,p,m,4,True,True,np)
        np.testing.assert_allclose(np.array(out['tokens'])[2],expected['tokens'][2],atol=2e-6)

    def test_nested_runtime_consumes_multi_source_match_and_executes_effect(self):
        if not mx.metal.is_available():self.skipTest('Metal required')
        from device_join_transition import run_round
        from device_constructor_completion import compile_completion
        from device_scheduled_runtime import run
        from device_schedule import compile_schedule
        import test_device_constructor_completion as completion_helper
        recipe,_=query_fixture.fixture();s,_,m=fixture()
        recipe['tables'].append(dict(name='H',kind='constructor'))
        recipe['rules'][2]['slots'].append(dict(sort=dict(kind='eq',name='E'),definition='effect'))
        recipe['rules'][2]['effects']=[dict(kind='construct',call=dict(table='H'),args=[dict(slot=2)],dst=3)]
        for key in ('slots','slot_roots','slot_valid'):
            s[key]=np.concatenate([s[key],np.full((3,1),False if key=='slot_valid' else -1,s[key].dtype)],axis=1)
        dp=device_plan(compile_transition(recipe,2));cp=completion_helper.device_plan(compile_completion(recipe,4))
        schedule,meta=compile_schedule(dict(saturate=dict(run='s')),['s'])
        dev=lambda d:{k:mx.array(v) for k,v in d.items()}
        ds,dm,dc=map(dev,(s,m,schedule))
        out,n,marks=mx.compile(lambda state:run(state,[(0,dp)],dm,cp,dc,meta['repeat_slots'],mx.array([True]),mx.array(201),mx.array(256),mx.array(55),mx.array(True),mx.array(True),12,mx,query_kernel=run_round))(ds)
        mx.eval(out,n,marks)
        self.assertTrue(bool(marks['finished']));self.assertEqual(int(n),202)
        self.assertEqual(np.array(marks['run_changed'])[np.array(marks['run_done'])].tolist(),[True,False])
        self.assertEqual(np.array(out['slots'])[2,3],201)

    def test_every_witness_is_checked_even_when_not_primary(self):
        s,p,m=fixture();candidate,_=proposals(s,p,m,4,True,True,np)
        for field in ('generation','visible','token_dirty','settled'):
            changed={k:v.copy() for k,v in s.items()}
            if field=='generation':changed[field][1]+=1
            else:changed[field][1]=(field=='token_dirty')
            out,marks=commit(changed,candidate,np)
            self.assertFalse(marks['accepted'].any(),field);self.assertFalse(out['present'][2])

    def test_multi_source_never_transfers_primary_and_incomplete_query_is_marked(self):
        s,p,m=fixture();candidate,_=proposals(s,p,m,4,True,True,np)
        candidate['transfer_covered'][:]=True
        _,marks=commit(s,candidate,np);self.assertFalse(marks['transferred'].any());self.assertTrue(marks['transfer_blocked'].any())
        out,marks=step(s,p,m,4,False,True,np)
        self.assertFalse(marks['query_complete']);self.assertTrue(marks['admission']['needs_attention'])


if __name__=='__main__':unittest.main()

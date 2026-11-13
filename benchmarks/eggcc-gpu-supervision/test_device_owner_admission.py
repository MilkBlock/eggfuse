import unittest
from copy import deepcopy
import numpy as np
import mlx.core as mx
from test_device_slot_owners import fixture
from test_device_join_transition import device_plan
from device_slot_owners import pack,transfer,read
from device_join_transition import compile_transition,step


def setup():
    recipe,state,takeover=fixture();recipe['rules'].append(deepcopy(recipe['rules'][1]))
    state['keys']=np.array([[0,7,91,-1],[1,7,91,92]],np.int32)
    for key,v in list(state.items()):state[key]=np.concatenate([v,np.zeros((1,)+v.shape[1:],v.dtype)])
    state['keys'][2]=-1;state['slot_valid'][2]=False
    state['active']=np.array([True,True,False]);state['readers']=np.array([True,True,False]);state['token_dirty']=np.zeros(3,bool)
    rng=np.random.default_rng(13);state['tokens']=rng.normal(0,.1,(3,128)).astype(np.float32)
    state=pack(state)
    # Three logical identities, but capacity for only two physical payloads.
    for key in list(state):
        if key.startswith('owner_') and key not in ('owner_epoch','owner_projection'):state[key]=state[key][:2]
    model=dict(w=rng.normal(0,.01,(1408,16)).astype(np.float32),coef=rng.normal(0,.01,(1425,128)).astype(np.float32))
    return recipe,state,takeover,model


class OwnerAdmission(unittest.TestCase):
    def test_gpu_match_allocates_released_owner_without_losing_old_queries(self):
        recipe,state,takeover,model=setup();plan=device_plan(compile_transition(recipe,2))
        dm={k:mx.array(v) for k,v in model.items()}
        tp={k:mx.array(v) if isinstance(v,np.ndarray) else v for k,v in takeover.items()}
        def run(s):
            s,tm=transfer(s,tp,mx.array(0),mx.array(1),mx.array(2),mx.array(5),mx.array(True),mx)
            s,first=step(s,plan,dm,8,mx.array(True),mx.array(True),mx)
            s,second=step(s,plan,dm,8,mx.array(True),mx.array(True),mx)
            return s,tm,first,second
        out,tm,first,second=mx.compile(run)({k:mx.array(v) for k,v in state.items()});mx.eval(out,tm,first,second)
        self.assertTrue(bool(tm['transferred']));self.assertEqual(np.array(first['admission']['accepted']).sum(),1)
        self.assertFalse(np.array(second['admission']['accepted']).any())
        np.testing.assert_array_equal(np.array(out['slot_owner']),[1,1,0])
        self.assertEqual(int(out['owner_generation'][0]),3);self.assertEqual(int(out['owner_epoch'][2]),3)
        self.assertNotIn('slots',out);self.assertNotIn('slot_valid',out)
        np.testing.assert_array_equal(np.array(out['owner_slots'])[0],[7,91,92])
        result={k:np.array(v) for k,v in out.items()}
        np.testing.assert_array_equal(read(result,'slots',np.array(0),np.array([0,1]),np),[7,91])
        self.assertFalse(read(result,'slot_valid',np.array(0),np.array(2),np))
        self.assertTrue(result['present'].all());self.assertTrue(result['settled'].all())

    def test_physical_capacity_is_not_logical_capacity(self):
        recipe,state,_,model=setup();out,marks=step(state,compile_transition(recipe,2),model,8,True,True,np)
        self.assertFalse(marks['admission']['accepted'].any());self.assertTrue(marks['admission']['owner_capacity'].any())
        self.assertTrue(marks['admission']['needs_attention']);self.assertFalse(out['present'][2])
        np.testing.assert_array_equal(out['owner_slots'],state['owner_slots'])

    def test_exhausted_physical_generation_does_not_wrap(self):
        recipe,state,takeover,model=setup()
        state,_=transfer(state,takeover,np.array(0),np.array(1),np.array(2),np.array(5),np.array(True),np)
        state['owner_generation'][0]=2147483647
        out,marks=step(state,compile_transition(recipe,2),model,8,True,True,np)
        self.assertFalse(marks['admission']['accepted'].any())
        self.assertTrue(marks['admission']['owner_capacity'].any())
        self.assertEqual(out['owner_generation'][0],2147483647)

    def test_single_source_entry_allocates_owner_and_keeps_scalar_columns(self):
        from test_device_entry_transition import EntryTransition
        from device_entry_transition import step as entry_step
        state,plan,layout,coeff,model=EntryTransition().fixture()
        state['scalar_numbers']=np.array([[3,5,9],[0,0,0],[0,0,0]],np.float32)
        state['scalar_numeric']=np.ones((3,3),bool);state['scalar_codes']=np.zeros((3,3,64),np.float32);state['scalar_valid']=np.ones((3,3),bool)
        out,marks=entry_step(pack(state),plan,layout,coeff,model,np.array(0),np)
        self.assertTrue(marks['admission']['accepted'][0])
        np.testing.assert_array_equal(out['owner_scalar_numbers'][1],[3,9,0])
        self.assertNotIn('scalar_numbers',out)
        self.assertEqual(out['slot_owner'][1],1)

    def test_allocation_does_not_complete_pending_effects(self):
        recipe,state,takeover,model=setup()
        recipe['rules'][2]['effects']=[dict(kind='union',args=[dict(slot=0),dict(slot=1)])]
        state,_=transfer(state,takeover,np.array(0),np.array(1),np.array(2),np.array(5),np.array(True),np)
        out,marks=step(state,compile_transition(recipe,2),model,8,True,True,np)
        self.assertTrue(marks['admission']['accepted'].any());self.assertFalse(out['settled'][2])
        self.assertEqual(out['effect_pc'][2],0);self.assertTrue(marks['admission']['needs_attention'])

    def test_stale_owner_blocks_match_and_admission(self):
        recipe,state,_,model=setup();state['owner_epoch'][0]+=1
        out,marks=step(state,compile_transition(recipe,2),model,8,True,True,np)
        self.assertFalse(marks['query_complete']);self.assertTrue(marks['admission']['needs_attention'])
        self.assertFalse(out['present'][2])

if __name__=='__main__':unittest.main()

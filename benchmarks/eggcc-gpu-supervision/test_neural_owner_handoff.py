import unittest
import numpy as np
import mlx.core as mx
from device_slot_owners import pack,read
from neural_owner_handoff import handoff
from test_device_slot_owners import fixture


class NeuralOwnerHandoff(unittest.TestCase):
    def test_generated_token_and_storage_are_adopted_atomically(self):
        _,state,plan=fixture();state['tokens']=np.zeros((2,128),np.float32)
        state=pack(state);dp={k:mx.array(v) if isinstance(v,np.ndarray) else v for k,v in plan.items()}
        token=mx.tanh(mx.arange(128,dtype=mx.float32)/128)
        out,marks=mx.compile(lambda s:handoff(s,dp,mx.array(0),mx.array(1),mx.array(2),mx.array(5),mx.array(2.),token,mx.array(True),mx.array(True),mx))({k:mx.array(v) for k,v in state.items()})
        mx.eval(out,marks)
        self.assertTrue(bool(marks['token_adopted']));self.assertEqual(int(marks['released_rows']),1)
        np.testing.assert_array_equal(out['tokens'][1],token)
        np.testing.assert_array_equal(out['tokens'][0],state['tokens'][0])
        after={k:np.array(v) for k,v in out.items()};after['owner_slots'][0]=999
        np.testing.assert_array_equal(read(after,'slots',np.array(0),np.array([0,1]),np),[7,91])

    def test_rejected_or_stale_proposal_changes_no_state(self):
        _,base,plan=fixture();base['tokens']=np.zeros((2,128),np.float32)
        for case in ('uncertified','nan','rejected','stale','busy','mismatch'):
            state=pack(base)
            if case=='mismatch':state['owner_slots']=state['owner_slots'].copy();state['owner_slots'][1,0]=123
            token=np.ones(128,np.float32)
            if case=='nan':token[0]=np.nan
            for xp in (np,mx):
                device={k:xp.array(v) for k,v in state.items()}
                dp={k:xp.array(v) if isinstance(v,np.ndarray) else v for k,v in plan.items()}
                out,marks=handoff(device,dp,xp.array(0),xp.array(1),xp.array(9 if case=='stale' else 2),xp.array(5),xp.array(-1. if case=='rejected' else 1.),xp.array(token),xp.array(case!='uncertified'),xp.array(case!='busy'),xp)
                self.assertFalse(bool(marks['transferred']),case)
                for k in state:np.testing.assert_array_equal(out[k],state[k],err_msg=case+':'+k)


if __name__=='__main__':unittest.main()

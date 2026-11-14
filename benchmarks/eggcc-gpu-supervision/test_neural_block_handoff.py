import unittest
import numpy as np
import mlx.core as mx
from test_device_slot_owners import fixture
from device_slot_owners import pack
from neural_block_handoff import initialize,handoff
from neural_device_candidates import compile_frames,compile_candidates,candidates
from audit_snapshot_queries import device


class BlockHandoff(unittest.TestCase):
    def test_old_and_new_entries_read_distinct_blocks_of_one_owner(self):
        recipe,state,plan=fixture();state['tokens']=np.zeros((2,128),np.float32)
        host=initialize(pack(state),np);blocks=mx.stack([mx.ones(128),mx.full((128,),2.)])
        def flow(s):return handoff(s,device(plan),mx.array(0),mx.array(1),mx.array(2),mx.array(5),mx.array(1.),blocks,mx.array(True),mx.array(True),mx)
        out,marks=mx.compile(flow)(device(host));mx.eval(out,marks)
        self.assertTrue(bool(marks['semantic_blocks_adopted']))
        np.testing.assert_array_equal(out['token_source'],[1,1]);np.testing.assert_array_equal(out['token_block'],[0,1])
        # Direct lookup includes resident source as context; its old token is zero.
        batch=candidates(out,device(compile_frames(recipe,3)),device(compile_candidates(recipe,recipe['rules'][0],context_capacity=2)),mx.array(True),mx.array(True),mx)
        mx.eval(batch)
        source=np.array(batch['sources']);mask=np.array(batch['mask'])&np.array(batch['live'])[:,None]
        values=np.array(batch['tokens'])-np.array(batch['source_tags'])
        for i,j in zip(*np.where(mask)):
            np.testing.assert_allclose(values[i,j],np.full(128,1+int(source[i,j])),atol=1e-6)
        self.assertTrue(bool(batch['complete']))
        stale=dict(out,generation=out['generation']+mx.array([0,1]))
        batch=candidates(stale,device(compile_frames(recipe,3)),device(compile_candidates(recipe,recipe['rules'][0])),mx.array(True),mx.array(True),mx)
        self.assertFalse(bool(batch['complete']))
        # A two-block owner cannot silently be compressed by a singleton join.
        _,again=flow(out);self.assertTrue(bool(again['block_capacity_boundary']))

    def test_rejected_block_handoff_is_atomic(self):
        _,state,plan=fixture();state['tokens']=np.zeros((2,128),np.float32);state=initialize(pack(state),np)
        out,marks=handoff(state,plan,np.array(0),np.array(1),np.array(2),np.array(5),np.array(1.),np.ones((2,128),np.float32),np.array(False),np.array(True),np)
        self.assertFalse(marks['semantic_blocks_adopted'])
        for key in state:np.testing.assert_array_equal(out[key],state[key])


if __name__=='__main__':unittest.main()

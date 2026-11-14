import unittest
from copy import deepcopy
import numpy as np
import mlx.core as mx
from test_device_slot_owners import fixture
from device_slot_owners import pack,compile_transfer
from neural_semantic_owner import initialize,resolve,compile_semantic_transfer
from neural_owner_handoff import handoff
from neural_device_candidates import compile_frames,compile_candidates,candidates
from audit_snapshot_queries import device


class SemanticOwner(unittest.TestCase):
    def test_compiler_requires_facts_not_just_same_fields(self):
        recipe,_,plan=fixture()
        self.assertTrue(compile_semantic_transfer(recipe,plan)['covered'])
        recipe['rules'][1]['query'][0]['call']['table']='G'
        self.assertFalse(compile_semantic_transfer(recipe,plan)['covered'])

    def test_union_requires_destination_proof(self):
        recipe,_,plan=fixture()
        recipe['rules'][0]['effects']=[dict(kind='union',args=[dict(slot=0),dict(slot=1)])]
        self.assertFalse(compile_semantic_transfer(recipe,plan)['covered'])
        recipe['rules'][1]['effects']=deepcopy(recipe['rules'][0]['effects'])
        self.assertTrue(compile_semantic_transfer(recipe,plan)['covered'])

    def test_gpu_alias_reads_new_token_and_owner_roles(self):
        recipe,state,plan=fixture();state['tokens']=np.zeros((2,128),np.float32)
        state=initialize(pack(state),np)
        plan=dict(plan,semantic_covered=compile_semantic_transfer(recipe,plan)['covered'])
        def flow(s):
            out,marks=handoff(s,device(plan),mx.array(0),mx.array(1),mx.array(2),mx.array(5),mx.array(1.),mx.ones(128),mx.array(True),mx.array(True),mx)
            return out,marks
        out,marks=mx.compile(flow)(device(state));mx.eval(out,marks)
        self.assertTrue(bool(marks['semantic_adopted']))
        np.testing.assert_array_equal(out['token_source'],[1,1])
        # Retain old logical witness and its projection; consume new owner's token.
        # Hide duplicate F from the destination's query-view only, so source=0 wins.
        view_recipe=deepcopy(recipe);view_recipe['rules'][1]['query']=view_recipe['rules'][1]['query'][1:]
        batch=candidates(out,device(compile_frames(recipe,3)),device(compile_candidates(view_recipe,recipe['rules'][0])),mx.array(True),mx.array(True),mx)
        mx.eval(batch);live=np.array(batch['live']);self.assertEqual(int(live.sum()),1)
        self.assertEqual(int(np.array(batch['sources'])[live][0,0]),0)
        self.assertEqual(int(np.array(batch['token_sources'])[live][0,0]),1)
        np.testing.assert_array_equal(np.array(batch['tokens'])[live][0,0],np.ones(128))
        np.testing.assert_array_equal(np.array(batch['binding_roots'])[live][0],[7,10])
        from neural_snapshot_candidates import relational_edges
        from device_slot_owners import read
        frames=device(compile_frames(recipe,3));rr=mx.arange(2)[:,None];ss=mx.arange(3)[None,:]
        labels=mx.where(read(out,'slot_valid',rr,ss,mx),read(out,'slot_roots',rr,ss,mx),-1)
        expected=relational_edges(labels,frames['roles'][out['keys'][:,0]],batch['token_sources'])
        np.testing.assert_allclose(batch['edges'],expected,atol=1e-6)
        # A retired or reused semantic owner cannot validate old aliases.
        stale=dict(out,generation=out['generation']+mx.array([0,1]))
        self.assertFalse(bool(resolve(stale,mx)[1][0]))

    def test_composed_aliases_and_uncovered_transfer(self):
        recipe,state,plan=fixture()
        for key,value in list(state.items()):state[key]=np.concatenate([value,value[1:]],axis=0)
        state['tokens']=np.zeros((3,128),np.float32);state=initialize(pack(state),np)
        def hop(state,plan,s,t,gs,gt,covered):
            return handoff(state,dict(plan,semantic_covered=covered),np.array(s),np.array(t),np.array(gs),np.array(gt),np.array(1.),np.ones(128,np.float32)*(t+1),np.array(True),np.array(True),np)
        out,m=hop(state,plan,0,1,2,5,True);self.assertTrue(m['semantic_adopted'])
        second=compile_transfer(recipe,dict(producer=1,consumer=1,projection=[0,1,2],projection_valid=[True]*3),3)
        out,m=hop(out,second,1,2,5,5,True)
        self.assertTrue(m['semantic_adopted']);np.testing.assert_array_equal(out['token_source'],[2,2,2])
        out,m=hop(state,plan,0,1,2,5,False)
        self.assertFalse(m['semantic_adopted']);np.testing.assert_array_equal(out['token_source'],[0,1,2])


if __name__=='__main__':unittest.main()

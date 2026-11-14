import unittest
import numpy as np
import mlx.core as mx
from test_neural_cell_chains import recipe
from device_snapshot_import import prepare_family
from device_slot_owners import pack
from neural_device_candidates import compile_frames,compile_candidates
from device_neural_speculation import compile_frame
from device_neural_step import advance,key_view
from audit_snapshot_queries import device


class Model:
    def transition(self,tokens,edges,mask,request,relations):
        return mx.ones(len(tokens)),mx.tanh(mx.sum(tokens*mask[...,None],axis=1)+.1)


def fixture(spare):
    r=recipe();r['rules'][0]['effects'][0]['sort']=r['rules'][0]['slots'][0]['sort']
    snapshot=dict(rows=[dict(table='F',values=[dict(sort='E',eq='0'),dict(sort='E',eq='1')],subsumed=False)])
    local,state,ids,_=prepare_family(r,snapshot,[0],spare)
    frames=device(compile_frames(local,3));query=device(compile_candidates(local,local['rules'][0],atoms=1,fields=2))
    frame=compile_frame(local['rules'][0],3,3,local,True)
    return device(pack(state)),mx.arange(32),mx.array(len(ids)),frames,query,frame


class DeviceStep(unittest.TestCase):
    def test_sealed_run_cannot_match_its_new_facts_until_next_run(self):
        state,roots,next_id,frames,query,frame=fixture(3)
        head=lambda token,request:mx.full((len(token),3),-1.)
        first,r1,n1,event=advance(state,roots,next_id,frames,query,frame,0,Model(),head,mx.array(True),mx,query_state=state)
        self.assertTrue(bool(event['admitted']))
        same,r2,n2,done=advance(first,r1,n1,frames,query,frame,0,Model(),head,mx.array(True),mx,query_state=state)
        self.assertFalse(bool(done['admitted']));self.assertTrue(bool(done['no_novel_proposal']))
        self.assertFalse(bool(done['needs_attention']))
        np.testing.assert_array_equal(same['keys'],first['keys']);self.assertEqual(int(n2),int(n1))
        later,r3,n3,next_event=advance(same,r2,n2,frames,query,frame,0,Model(),head,mx.array(True),mx,query_state=same)
        self.assertTrue(bool(next_event['admitted']))
        np.testing.assert_array_equal(later['keys'][2],[0,1,4])
        self.assertGreater(int(n3),int(n2))

    def test_stale_ancestor_blocks_fresh_allocation_and_requests_audit(self):
        from device_witness_context import initialize
        state,roots,next_id,frames,query,frame=fixture(3)
        state=initialize(state,1,mx)
        for site in frame['witness_sites'].values():site['context_depth']=1
        head=lambda token,request:mx.full((len(token),3),-1.)
        first,r1,n1,event=advance(state,roots,next_id,frames,query,frame,0,Model(),head,mx.array(True),mx)
        self.assertTrue(bool(event['admitted']))
        for column,value in (('generation',99),('visible',False),('present',False),('owner_generation',99)):
            stale=dict(first);stale[column]=stale[column].at[0].add(value-stale[column][0]) if column in ('generation','owner_generation') else stale[column].at[0].multiply(False)
            second,r2,n2,marks=advance(stale,r1,n1,frames,query,frame,0,Model(),head,mx.array(True),mx)
            if column=='owner_generation':self.assertTrue(bool(marks['query_incomplete']))
            else:self.assertTrue(bool(marks['stale_witness_context']),column)
            self.assertTrue(bool(marks['needs_attention']),column)
            self.assertFalse(bool(marks['admitted']),column)
            self.assertFalse(bool(marks['no_novel_proposal']),column)
            np.testing.assert_array_equal(second['present'],stale['present'])
            np.testing.assert_array_equal(r2,r1);self.assertEqual(int(n2),int(n1))

    def test_two_device_steps_share_state_without_teacher_or_intermediate_host_read(self):
        state,roots,next_id,frames,query,frame=fixture(3)
        head=lambda token,request:mx.full((len(token),3),-1.)
        first,r1,n1,m1=advance(state,roots,next_id,frames,query,frame,0,Model(),head,mx.array(True),mx)
        second,r2,n2,m2=advance(first,r1,n1,frames,query,frame,0,Model(),head,mx.array(True),mx)
        mx.eval(second,r2,n2,m1,m2)
        self.assertTrue(bool(m1['admitted']) and bool(m2['admitted']))
        self.assertEqual(int(mx.sum(second['present'])),3)
        self.assertEqual(int(n2),8)
        np.testing.assert_array_equal(second['keys'][1:3],[[0,0,1],[0,1,4]])
        np.testing.assert_array_equal(second['owner_slots'][2],[1,4,7])
        self.assertEqual(int(r2[4]),4);self.assertEqual(int(r2[7]),7)
        self.assertGreater(int(m2['duplicate_candidates']),0)
        self.assertFalse(bool(m2['needs_attention']))
        self.assertFalse(np.array_equal(first['tokens'][1],second['tokens'][2]))

    def test_capacity_and_disabled_step_are_not_saturation(self):
        state,roots,next_id,frames,query,frame=fixture(1)
        head=lambda token,request:mx.full((len(token),3),-1.)
        first,r1,n1,_=advance(state,roots,next_id,frames,query,frame,0,Model(),head,mx.array(True),mx)
        second,r2,n2,marks=advance(first,r1,n1,frames,query,frame,0,Model(),head,mx.array(True),mx)
        self.assertTrue(bool(marks['capacity']));self.assertTrue(bool(marks['needs_attention']))
        self.assertFalse(bool(marks['no_novel_proposal']))
        np.testing.assert_array_equal(r1,r2);self.assertEqual(int(n1),int(n2))
        _,_,_,disabled=advance(first,r1,n1,frames,query,frame,0,Model(),head,mx.array(False),mx)
        self.assertFalse(bool(disabled['admitted']));self.assertFalse(bool(disabled['no_novel_proposal']))

    def test_comparison_uses_equivalence_without_rewriting_keys(self):
        keys=mx.array([[3,2,-1],[3,1,-1]])
        view,valid=key_view(keys,mx.array([0,1,1]),mx)
        np.testing.assert_array_equal(view,[[3,1,-1],[3,1,-1]])
        self.assertTrue(bool(mx.all(valid)));self.assertEqual(int(keys[0,1]),2)


if __name__=='__main__':unittest.main()

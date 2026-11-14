import unittest
import numpy as np
import mlx.core as mx
from test_neural_gpu_rhs import fixture
from audit_neural_gpu_rhs import initial_case,audit_failed
from audit_snapshot_queries import device
from device_constructor_completion import complete
from neural_device_candidates import compile_frames,compile_candidates,candidates,encode_seeds
from neural_owner_handoff import handoff


class DeviceCandidates(unittest.TestCase):
    def prepared(self):
        recipe,record=fixture();local,state,plan,ctx,tp,src,dst,n,_=initial_case(recipe,record)
        out,_,marks=complete(device(state),device(plan),mx.array(n),mx.array(len(ctx['roots'])),mx.array(64),mx.array(True),mx.array(True),mx,device(ctx),eq_rounds=8)
        out,_=handoff(out,device(tp),mx.array(src),mx.array(dst),mx.array(1),mx.array(1),mx.array(2.),mx.ones(128),mx.array(True),mx.array(True),mx)
        return recipe,local,out,device(compile_frames(local,state['owner_projection'].shape[1])),dst

    def test_seed_encoding_matches_initial_interface_and_preserves_generated_tokens(self):
        from neural_cell_transition import CellTransition
        from multi_entry_ridge import template
        from device_slot_owners import read
        recipe,record=fixture();local,host,_,_,_,src,dst,_,_=initial_case(recipe,record)
        model=CellTransition(640,32);layout=compile_frames(local,host['owner_projection'].shape[1])
        output=encode_seeds(device(host),device(layout),model,mx)
        for row,rid in enumerate(host['keys'][:,0]):
            if not layout['seed'][rid]:
                np.testing.assert_array_equal(output['tokens'][row],host['tokens'][row]);continue
            rule=local['rules'][rid];roles,_=template(rule);n=len(rule['slots'])
            roots=read(host,'slot_roots',np.array(row),np.arange(n),np);x=np.zeros(640,np.float32)
            for slot in range(n):x[slot*128:(slot+1)*128]=np.concatenate([roles[slot],np.tanh(roles[roots==roots[slot]].sum(axis=0))])
            np.testing.assert_allclose(output['tokens'][row],model.encode(mx.array(x)[None,:])[0],atol=2e-6)

    def test_next_inputs_read_gpu_result_after_ownership_transfer(self):
        recipe,local,state,frames,target=self.prepared()
        plan=compile_candidates(local,recipe['rules'][0])
        batch=candidates(state,frames,device(plan),mx.array(True),mx.array(True),mx)
        live=np.array(batch['live']);values=np.array(batch['binding_roots'])[live]
        self.assertTrue(bool(batch['complete']))
        self.assertEqual(set(map(tuple,values)),{(0,1),(1,2),(2,3)})
        new=np.flatnonzero(live & (np.array(batch['binding_roots'])[:,0]==2))[0]
        self.assertEqual(int(batch['sources'][new,0]),target)
        np.testing.assert_array_equal(batch['tokens'][new,0],np.ones(128))

    def test_type_routing_does_not_prefilter_invalid_bindings(self):
        recipe,local,state,frames,_=self.prepared();eq=recipe['tables'][0]['schema'][0]
        consumer=dict(slots=[dict(sort=eq,definition='query') for _ in range(3)],query=[dict(call=dict(table='F'),args=[dict(slot=0),dict(slot=s)]) for s in (1,2)],effects=[])
        batch=candidates(state,frames,device(compile_candidates(local,consumer)),mx.array(True),mx.array(True),mx)
        live=np.array(batch['live']);self.assertEqual(int(live.sum()),9)
        relation=np.array(batch['relations'])[live];half=relation.shape[1]//2
        valid=np.all((relation[:,half:]==0)|(relation[:,:half]>0),axis=1)
        self.assertEqual(int(valid.sum()),3)

    def test_follow_errors_fail_the_audit_even_if_rhs_passes(self):
        good=dict(pending=False,graph=dict(passed=True),facts_decoded=True,interfaces_preserved=True,token_retained=True)
        self.assertFalse(audit_failed([good]))
        self.assertTrue(audit_failed([good],True))
        for key in ('false_positive','missed','incomplete_rules','invalid_predictions'):
            self.assertTrue(audit_failed([dict(good,follow=dict(counts={key:1}))],True))
        self.assertTrue(audit_failed([dict(good,follow=dict(counts={}))],True))
        counts={k:0 for k in ('false_positive','missed','incomplete_rules','invalid_predictions')}
        self.assertFalse(audit_failed([dict(good,follow=dict(counts=counts))],True))

    def test_overflow_blocks_complete_enumeration_claim(self):
        recipe,local,state,frames,_=self.prepared()
        batch=candidates(state,frames,device(compile_candidates(local,recipe['rules'][0],capacity=2)),mx.array(True),mx.array(True),mx)
        self.assertTrue(bool(batch['overflow']));self.assertFalse(bool(batch['complete']))


if __name__=='__main__':unittest.main()

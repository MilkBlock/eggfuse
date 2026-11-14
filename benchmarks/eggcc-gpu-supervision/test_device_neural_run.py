import unittest
from copy import deepcopy
import mlx.core as mx
from test_device_neural_step import Model
from test_neural_cell_chains import recipe
from device_snapshot_import import prepare_family
from device_slot_owners import pack
from neural_device_candidates import compile_frames,compile_candidates
from device_neural_speculation import compile_frame
from audit_snapshot_queries import device
from device_neural_run import execute
from reference_cell_closure import facts_from_cells
import numpy as np


class SourceRun(unittest.TestCase):
    def fixture(self):
        r=recipe();first=r['rules'][0];first['effects'][0]['call']['table']='G';first['effects'][0]['sort']=first['slots'][0]['sort']
        second=deepcopy(first);second['query'][0]['call']['table']='G';second['effects'][0]['call']['table']='H'
        r['rules'].append(second)
        for name in ('G','H'):r['tables'].append(dict(r['tables'][0],name=name))
        snapshot=dict(rows=[dict(table='F',values=[dict(sort='E',eq='0'),dict(sort='E',eq='1')],subsumed=False)])
        local,state,ids,_=prepare_family(r,snapshot,[0,1],4)
        plans=[(i,device(compile_candidates(local,local['rules'][i],atoms=1,fields=2)),compile_frame(local['rules'][i],3,3,local,True)) for i in range(2)]
        return local,device(pack(state)),mx.arange(64),mx.array(len(ids)),device(compile_frames(local,3)),plans

    def test_later_rule_observes_new_cell_only_in_next_run(self):
        local,state,roots,n,frames,plans=self.fixture();head=lambda t,r:mx.full((len(t),3),-1.)
        first,r1,n1,m1=execute(state,roots,n,frames,plans,Model(),head,2,mx)
        self.assertTrue(bool(m1['query_exhausted']));self.assertEqual(int(m1['admitted']),1)
        facts,_=facts_from_cells(local,{k:np.array(v) for k,v in first.items()})
        self.assertEqual({t for t,_,_ in facts},{'F','G'})
        second,r2,n2,m2=execute(first,r1,n1,frames,plans,Model(),head,2,mx)
        self.assertTrue(bool(m2['query_exhausted']));self.assertEqual(int(m2['admitted']),1)
        facts,_=facts_from_cells(local,{k:np.array(v) for k,v in second.items()})
        self.assertEqual({t for t,_,_ in facts},{'F','G','H'})
        _,_,_,m3=execute(second,r2,n2,frames,plans,Model(),head,2,mx)
        self.assertTrue(bool(m3['query_exhausted']));self.assertEqual(int(m3['admitted']),0)

    def test_current_state_runs_ignore_poisoned_historical_latents(self):
        from device_current_cell_inputs import current_candidates
        class CurrentModel(Model):
            def current_candidate_batch(self, state, frames, plan, xp):
                encoder=lambda x:xp.tanh(x.reshape(len(x),-1,128).sum(axis=1))
                return current_candidates(state,frames,plan,encoder,
                                          xp.array(True),xp.array(True),xp)
        local,state,roots,n,frames,plans=self.fixture()
        head=lambda t,r:mx.full((len(t),3),-1.)
        model=CurrentModel()
        for expected in ({'F','G'},{'F','G','H'},{'F','G','H'}):
            state=dict(state,tokens=mx.full_like(state['tokens'],float('nan')),
                       token_dirty=mx.ones_like(state['present']))
            state,roots,n,report=execute(state,roots,n,frames,plans,model,head,2,mx)
            self.assertTrue(bool(report['query_exhausted']))
            self.assertFalse(bool(report['needs_attention']))
            facts,covered=facts_from_cells(local,{k:np.array(v) for k,v in state.items()})
            self.assertTrue(covered)
            self.assertEqual({t for t,_,_ in facts},expected)
        self.assertEqual(int(report['admitted']),0)
        # Opting into current-state execution must not certify old latents.
        self.assertTrue(bool(mx.any(state['token_dirty'] & state['present'])))
        _,_,_,old=execute(state,roots,n,frames,plans,Model(),head,2,mx)
        self.assertTrue(bool(old['needs_attention']))

    def test_budget_or_disabled_run_cannot_claim_query_exhaustion(self):
        _,state,roots,n,frames,plans=self.fixture();head=lambda t,r:mx.full((len(t),3),-1.)
        _,_,_,m=execute(state,roots,n,frames,plans,Model(),head,1,mx)
        self.assertFalse(bool(m['query_exhausted']));self.assertTrue(bool(m['attempt_budget_exhausted']))
        self.assertFalse(bool(m['trace'][-1][1]['admitted']))
        _,_,_,off=execute(state,roots,n,frames,plans,Model(),head,2,mx,enabled=False)
        self.assertFalse(bool(off['query_exhausted']));self.assertFalse(bool(off['attempt_budget_exhausted']))
        self.assertEqual(int(off['admitted']),0)


if __name__=='__main__':unittest.main()

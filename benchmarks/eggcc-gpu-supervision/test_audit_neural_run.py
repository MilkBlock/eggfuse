import unittest
import mlx.core as mx
import test_device_neural_run as fixtures
from test_device_neural_step import Model
from device_neural_run import execute
from audit_neural_run import audit
from reference_union_family import Reference
from device_snapshot_import import identity
from device_schedule import compile_schedule,initial,tick,current
from audit_snapshot_queries import device


class RunAudit(unittest.TestCase):
    def reference(self,local):
        values=[dict(sort='E',eq=str(i)) for i in range(2)]
        return Reference(local,[dict(table='F',values=values)],{identity(v):i for i,v in enumerate(values)})

    def test_original_schedule_advances_only_after_full_run_audit(self):
        local,state,roots,n,frames,plans=fixtures.SourceRun().fixture();ref=self.reference(local)
        plan,meta=compile_schedule({'sequence':[{'run':'first'},{'run':'second'}]},['first','second'])
        plan=device(plan);control=initial(plan,meta['repeat_slots'],mx)
        head=lambda t,r:mx.full((len(t),3),-1.)
        for i in range(2):
            stage,halted=current(control,plan,mx);self.assertEqual(int(stage),i);self.assertFalse(bool(halted))
            state,roots,n,result=execute(state,roots,n,frames,[plans[i]],Model(),head,2,mx)
            ref,verdict=audit(local,ref,[local['rules'][i]],state,roots,n,2,result)
            self.assertEqual(verdict['status'],'pass');self.assertTrue(verdict['run_changed'])
            control,_=tick(control,plan,verdict['run_done'],verdict['run_changed'],mx)
        self.assertTrue(bool(current(control,plan,mx)[1]))
        self.assertEqual({t for t,v in ref.normalized_facts()},{'F','G','H'})

    def test_silent_model_cannot_advance_schedule(self):
        class Silent(Model):
            def transition(self,*args):
                logits,tokens=super().transition(*args);return -logits,tokens
        local,state,roots,n,frames,plans=fixtures.SourceRun().fixture();ref=self.reference(local)
        out,rr,nn,result=execute(state,roots,n,frames,[plans[0]],Silent(),lambda t,r:mx.full((len(t),3),-1.),2,mx)
        self.assertTrue(bool(result['query_exhausted']))
        expected,verdict=audit(local,ref,[local['rules'][0]],out,rr,nn,2,result)
        self.assertFalse(verdict['run_done']);self.assertFalse(verdict['run_changed'])
        self.assertIn('fact_set_difference',verdict['graph']['errors'])
        plan,meta=compile_schedule({'run':'first'},['first']);plan=device(plan);control=initial(plan,meta['repeat_slots'],mx)
        unchanged,_=tick(control,plan,verdict['run_done'],verdict['run_changed'],mx)
        self.assertEqual(int(unchanged['pc']),0)
        self.assertEqual(len(ref.facts),1);self.assertEqual(len(expected.facts),2)

    def test_budget_end_does_not_certify_run_even_when_graph_matches(self):
        local,state,roots,n,frames,plans=fixtures.SourceRun().fixture();ref=self.reference(local)
        out,rr,nn,result=execute(state,roots,n,frames,[plans[0]],Model(),lambda t,r:mx.full((len(t),3),-1.),1,mx)
        _,verdict=audit(local,ref,[local['rules'][0]],out,rr,nn,2,result)
        self.assertTrue(verdict['graph']['passed']);self.assertFalse(verdict['run_done'])
        self.assertTrue(verdict['attempt_budget_exhausted'])


if __name__=='__main__':unittest.main()

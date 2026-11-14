import unittest
import mlx.core as mx
from test_neural_cell_chains import recipe
from test_device_neural_step import Model
from device_snapshot_import import prepare_family
from device_slot_owners import pack
from neural_device_candidates import compile_frames
from audit_snapshot_queries import device
from reference_union_family import Reference
from neural_cumulative import run


class Cumulative(unittest.TestCase):
    def evaluate(self,sweeps,productive=False,model=None,collector=None):
        r=recipe();rule=r['rules'][0]
        if productive:rule['effects'][0]['sort']=rule['slots'][0]['sort']
        else:rule['effects']=[dict(kind='copy',arg=dict(slot=1),dst=2)]
        snapshot=dict(rows=[dict(table='F',values=[dict(sort='E',eq='0'),dict(sort='E',eq='1')],subsumed=False)])
        local,state,ids,rows=prepare_family(r,snapshot,[0],2)
        local=dict(local,rules=local['rules']+[rule])
        return run(local,device(pack(state)),mx.arange(32),mx.array(len(ids)),
                   device(compile_frames(local,3)),[rule],model or Model(),lambda t,r:mx.full((len(t),3),-1.),
                   sweeps,Reference(r,rows,ids),{0:0,1:1},len(ids),collector=collector)

    def test_actual_cumulative_admission_and_independent_fixedpoint(self):
        result=self.evaluate(2)
        self.assertEqual(result['admitted'],1);self.assertEqual(result['replayed'],1)
        self.assertTrue(result['graph']['passed']);self.assertTrue(result['cpu_fixedpoint'])
        self.assertTrue(result['device_no_novel']);self.assertEqual(result['status'],'pass')

    def test_capture_labels_are_post_run_and_do_not_change_execution(self):
        samples=[];captured=self.evaluate(2,collector=samples);plain=self.evaluate(2)
        self.assertEqual(captured['graph'],plain['graph'])
        self.assertEqual(captured['admitted'],plain['admitted'])
        self.assertEqual(len(samples),1);self.assertEqual(samples[0]['token'].shape,(128,))
        self.assertEqual(samples[0]['eq_target'].tolist(),[0.,0.,1.])
        self.assertEqual(captured['capture_skipped_entries'],0)

    def test_model_silence_cannot_certify_fixedpoint(self):
        class Silent(Model):
            def transition(self,*args):
                logits,tokens=super().transition(*args)
                return -logits,tokens
        result=self.evaluate(2,productive=True,model=Silent())
        self.assertTrue(result['device_no_novel']);self.assertTrue(result['graph']['passed'])
        self.assertFalse(result['cpu_fixedpoint']);self.assertEqual(result['status'],'difference')

    def test_budget_end_is_not_device_saturation(self):
        result=self.evaluate(1)
        self.assertTrue(result['cpu_fixedpoint'])
        self.assertFalse(result['device_no_novel']);self.assertEqual(result['status'],'difference')


if __name__=='__main__':unittest.main()

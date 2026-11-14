import unittest
import numpy as np
from copy import deepcopy
from test_neural_cell_chains import recipe
from neural_cell_samples import samples
from neural_cell_chains import chains
from device_slot_owners import compile_transfer
from neural_combined_cell import compose
from neural_semantic_owner import compile_semantic_transfer


class CombinedCell(unittest.TestCase):
    def test_combined_template_covers_both_cells_and_keeps_target_slots(self):
        r=recipe();p=compile_transfer(r,dict(producer=0,consumer=0,projection=[1,2],projection_valid=[True,True]),6)
        c=compose(r,p);self.assertEqual(c['target_projection'],[0,1,2]);self.assertEqual(len(c['rule']['slots']),4)
        self.assertEqual(c['source_projection'],[3,0,1])
        rr=dict(r,rules=[r['rules'][0],c['rule']])
        proof=dict(p,consumer=1,copied=np.zeros(6,bool))
        self.assertTrue(compile_semantic_transfer(rr,proof)['covered'])
        target_plan=dict(proof,projection=np.arange(6,dtype=np.int32))
        self.assertTrue(compile_semantic_transfer(rr,target_plan)['covered'])
        self.assertEqual(compose(deepcopy(r),p)['identity'],c['identity'])

    def test_ordered_request_distinguishes_static_projection(self):
        from neural_combined_cell import request
        r=recipe();p=compile_transfer(r,dict(producer=0,consumer=0,projection=[1,2],projection_valid=[True,True]),6)
        a=compose(r,p);b=deepcopy(a);b['source_projection']=list(reversed(a['source_projection']))
        self.assertFalse(np.allclose(request(a),request(b)))

    def test_training_labels_retain_source_and_destination(self):
        r=recipe();records=[];samples(r,4,23,records,ordered=True)
        old,_=chains(r,records,ordered=True,eq_targets=True)
        joint,_=chains(r,records,ordered=True,eq_targets=True,combined_owner=True)
        self.assertTrue(joint['valid'].all());self.assertTrue(joint['source_eq_mask'].any());self.assertTrue(joint['target_eq_mask'].any())
        np.testing.assert_array_equal(old['parent'],joint['parent'])
        np.testing.assert_array_equal(old['relations'],joint['relations'])
        self.assertFalse(np.allclose(old['request'],joint['request']))
        self.assertFalse(np.allclose(old['target'],joint['target']))
        self.assertGreater(int(joint['eq_mask'].sum()),int(old['eq_mask'].sum()))


if __name__=='__main__':unittest.main()

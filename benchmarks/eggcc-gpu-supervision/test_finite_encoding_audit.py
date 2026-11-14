import unittest
import numpy as np
from finite_encoding_audit import audit


class EncodingAudit(unittest.TestCase):
    def data(self):
        result={k:np.zeros((3,2),np.float32) for k in ('edges','mask','replace','request','relations')}
        result.update(tokens=np.zeros((3,2,4)),seed_x=np.zeros((3,2,4)))
        result.update(valid=np.ones(3,bool),eq_target=np.array([[0],[1],[1]]),eq_mask=np.ones((3,1),bool))
        return result

    def test_conflicting_equal_inputs(self):
        result=audit(self.data())
        self.assertEqual(result['conflicting_samples'],2)
        self.assertEqual(result['unique_inputs'],1)

    def test_incidence_distinguishes_inputs(self):
        data=self.data();data['relations'][1:]=1
        self.assertEqual(audit(data)['conflicting_samples'],0)

    def test_masks_and_validity(self):
        data=self.data();data['eq_mask'][0]=False
        self.assertEqual(audit(data)['conflicting_samples'],0)
        data['valid'][0]=False
        self.assertEqual(audit(data)['conflicting_samples'],2)

    def test_unused_boundary_teacher_tokens_do_not_hide_conflicts(self):
        data=self.data();data['tokens'][1:]=123
        self.assertEqual(audit(data)['conflicting_samples'],2)

    def test_unused_owned_seeds_do_not_hide_conflicts(self):
        data=self.data();data['replace'][:]=True;data['seed_x'][1:]=123
        self.assertEqual(audit(data)['conflicting_samples'],2)


if __name__=='__main__':unittest.main()

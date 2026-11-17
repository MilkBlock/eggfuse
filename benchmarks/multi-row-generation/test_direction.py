import unittest
import numpy as np
import mlx.core as mx
from task import generate,audit,KEYS,VALUES
from verify import verify


def literal_output(d):
    columns=[]
    for k,width in enumerate((KEYS,KEYS,VALUES,VALUES)):
        columns.append(np.eye(width)[d['fields'][...,k]]*20-10)
    ptr=mx.array(d['targets']);return dict(pointers=ptr,field_logits=mx.array(np.concatenate(columns,-1),mx.float32),
        addresses=mx.stack((mx.array(d['coords_b'])[ptr[0]],mx.array(d['coords_pair'])[ptr[1]])))

class DirectionTests(unittest.TestCase):
    def test_training_direction_is_identifiable(self):
        d=generate(2,4,128,1200,'short_cycles')
        self.assertTrue(any(3 in key for key in d['cycle_keys']))
        self.assertTrue(all(max(key)<=3 for key in d['cycle_keys']))
        self.assertTrue(any(not np.array_equal(x,np.argsort(x)) for x in d['targets'][1]))

    def test_final_functional_graphs_do_not_overlap_permutation_family(self):
        d=generate(8,2,128,19403,'functional')
        for successors in d['targets'][1]:self.assertLess(len(set(successors.tolist())),16)
        result=literal_output(d);checked=verify(mx.array(d['a']),mx.array(d['b']),result,mx.array(d['coords_b']),mx.array(d['coords_pair']));mx.eval(checked)
        self.assertTrue(bool(mx.all(checked['whole_graph'])))
        cpu=audit(d,d['targets'],d['fields'],np.array(result['addresses']))
        self.assertEqual(cpu['whole_graph_passed'],128)

    def test_checker_rejects_instead_of_repairing(self):
        d=generate(2,3,4,55,'long_cycle');result=literal_output(d)
        bad=dict(result);bad['pointers']=mx.stack((result['pointers'][0],mx.zeros_like(result['pointers'][1])))
        before=np.array(bad['pointers']).copy()
        check=verify(mx.array(d['a']),mx.array(d['b']),bad,mx.array(d['coords_b']),mx.array(d['coords_pair']));mx.eval(check)
        self.assertFalse(bool(mx.any(check['whole_graph'])))
        np.testing.assert_array_equal(bad['pointers'],before)

if __name__=='__main__':unittest.main()

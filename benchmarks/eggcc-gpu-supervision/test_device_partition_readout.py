import unittest
import numpy as np
import mlx.core as mx
from device_partition_readout import compile_catalog,select,partitions
from token_eq_readout import pair_layout,static_equalities,quotient_layout,check_partition


def fixture(n=3,effects=None):
    rule=dict(query=[],effects=effects or [],slots=[dict(sort=dict(kind='eq',name='E')) for _ in range(n)])
    pairs,*_=pair_layout(rule);proof=static_equalities(rule,pairs)
    row=dict(pairs=pairs,static=proof,quotient=quotient_layout(rule,pairs,proof))
    return rule,row


class PartitionReadout(unittest.TestCase):
    def test_enumerates_all_small_partitions_and_preserves_static_equalities(self):
        self.assertEqual([len(partitions(i)) for i in range(6)],[1,1,2,5,15,52])
        r,row=fixture(3);p=compile_catalog(r,row)
        self.assertEqual(p['states'],5)
        for c in p['matrix']:
            self.assertFalse(check_partition(row['pairs'],np.zeros(3,bool),c)['nontransitive'])
        r,row=fixture(3,[dict(kind='union',args=[dict(slot=0),dict(slot=1)])])
        p=compile_catalog(r,row);self.assertEqual(p['states'],2)
        self.assertEqual(p['matrix'].shape,(2,1))
        self.assertFalse(compile_catalog(*fixture(6))['covered'])

    def test_compiled_gpu_rejects_inconsistent_triangle_without_blind_closure(self):
        p=compile_catalog(*fixture())['matrix']
        scores=np.array([[.9,.1,.6],[.5,.5,.5],[np.nan,.1,.1]],np.float32)
        expected,marks=select(scores,p,np)
        np.testing.assert_array_equal(expected[0],[1,0,0])
        self.assertTrue(marks['ambiguous'][1]);self.assertTrue(marks['nonfinite'][2])
        dm=mx.array(p)
        actual,am=mx.compile(lambda x:select(x,dm,mx))(mx.array(scores));mx.eval(actual,am)
        np.testing.assert_array_equal(np.array(actual),expected)
        np.testing.assert_array_equal(np.array(am['ready']),marks['ready'])

    def test_already_legal_threshold_predictions_are_preserved(self):
        from itertools import product
        r,row=fixture();matrix=compile_catalog(r,row)['matrix']
        for bits in product((False,True),repeat=3):
            scores=np.where(bits,.9,.1).astype(np.float32)[None]
            out,marks=select(scores,matrix,np)
            self.assertFalse(check_partition(row['pairs'],np.array(bits),out[0])['nontransitive'])
            if not check_partition(row['pairs'],np.array(bits),scores[0])['nontransitive']:
                np.testing.assert_array_equal(out[0],bits)

    def test_empty_quotient_is_one_proven_state(self):
        r,row=fixture(2,[dict(kind='union',args=[dict(slot=0),dict(slot=1)])])
        p=compile_catalog(r,row);self.assertEqual(p['matrix'].shape,(1,0))
        values,marks=select(np.empty((3,0),np.float32),p['matrix'],np)
        self.assertEqual(values.shape,(3,0));self.assertTrue(marks['ready'].all())

    def test_sort_groups_do_not_merge_and_budget_is_explicit(self):
        r,row=fixture(4)
        r['slots'][2]['sort']['name']='F';r['slots'][3]['sort']['name']='F'
        pairs,*_=pair_layout(r);proof=static_equalities(r,pairs)
        row=dict(pairs=pairs,static=proof,quotient=quotient_layout(r,pairs,proof))
        self.assertEqual(compile_catalog(r,row)['states'],4)
        self.assertFalse(compile_catalog(r,row,max_states=3)['covered'])

if __name__=='__main__':unittest.main()

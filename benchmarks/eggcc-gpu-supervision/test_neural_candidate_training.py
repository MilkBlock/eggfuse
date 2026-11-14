import unittest
import numpy as np
from neural_candidate_training import synthetic_snapshot, pooled_candidates
from neural_snapshot_candidates import import_interfaces
from reference_union_family import Reference
from test_neural_cell_chains import recipe


class PooledTraining(unittest.TestCase):
    def family(self):
        r=recipe(); eq=r['tables'][0]['schema'][0]
        r['rules'][0]['query'].append(dict(call=dict(table='F'),args=[dict(slot=1),dict(slot=2)]))
        r['rules'][0]['slots'][2]['definition']='query'
        r['rules'][0]['effects']=[]
        return r

    def test_generated_snapshot_is_canonical_and_reproducible(self):
        r=self.family(); snapshot=synthetic_snapshot(r,123,8)
        self.assertEqual(snapshot,synthetic_snapshot(r,123,8))
        rows,ids,*_=import_interfaces(r,snapshot)
        ref=Reference(r,rows,ids)
        self.assertEqual(ref.unions,0)
        self.assertGreater(len(ref.matches(r['rules'][0])),0)

    def test_bounded_pool_has_both_classes_and_all_expected_shapes(self):
        data,coverage=pooled_candidates(self.family(),123,examples=8,per_class=12)
        self.assertGreater(coverage[0]['positive_seen'],0)
        self.assertGreater(coverage[0]['negative_seen'],0)
        self.assertEqual(coverage[0]['scanned'],coverage[0]['candidates'])
        self.assertEqual(data['edges'].shape,(len(data['valid']),2,2,64))
        self.assertEqual(set(data['valid']),{0,1})
        self.assertTrue(np.isfinite(data['x']).all())
        self.assertTrue(np.isfinite(data['edges']).all())


if __name__=='__main__':unittest.main()

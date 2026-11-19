"""Focused tests for address ancestry, port permutations and relayout invariants."""
import unittest
import numpy as np
from data import audit, dataset, relayout


def gold(d):
    g = np.arange(len(d['value']))[:,None]
    p1, p2 = d['target1'].copy(), d['target2'].copy()
    pair_values = d['value'][g,p1]
    return [p1,p2,d['coords'][p1].copy(),pair_values,pair_values[g,p2]]


class AddressTask(unittest.TestCase):
    def test_deterministic_permutations_and_coverage(self):
        d = dataset(3,4,3,64,404)
        for name,arr in dataset(3,4,3,64,404).items():
            np.testing.assert_array_equal(d[name],arr)
            self.assertEqual(arr.dtype,np.int32)
        r = audit(d,*gold(d))
        self.assertEqual(r['whole_graphs'],64)
        for step in (r['run1'],r['run2']):
            self.assertEqual(step['correct'],64*36)
            self.assertEqual(step['same_row_correct']+step['cross_row_correct'],step['correct'])
            for category in ('self','sibling','same_row_different_cell','cross_row'):
                self.assertGreater(step[category+'_obligations'],0)
        n=len(d['coords']);idx=np.arange(n)
        for t,values in zip(d['target1'],d['value']):
            np.testing.assert_array_equal(np.sort(t),idx)
            self.assertTrue(any(len(set(cell))<len(cell) for cell in values.reshape(-1,3)))

    def test_cell_and_port_relayout_preserves_both_rules(self):
        before=dataset(3,2,3,19,321);after,mapping=relayout(before,2,3,331)
        batch,n=mapping.shape;g=np.arange(batch)[:,None]
        self.assertFalse(np.array_equal(mapping[0],mapping[1]))
        moved_cells=mapping.reshape(batch,6,3)//3
        np.testing.assert_array_equal(moved_cells,np.broadcast_to(moved_cells[...,:1],moved_cells.shape))
        ports=mapping.reshape(batch,6,3)%3
        self.assertTrue(any(not np.array_equal(cell,ports[0,0]) for cell in ports[0]))
        for i in range(batch):
            np.testing.assert_array_equal(np.sort(mapping[i]),np.arange(n))
            for old_slot,new_slot in enumerate(mapping[i]):
                for name in ('make_ref','finish_ref'):
                    source=tuple(before[name][i,old_slot]);address=np.flatnonzero((before['coords']==source).all(1))[0]
                    np.testing.assert_array_equal(after[name][i,new_slot],after['coords'][mapping[i,address]])
        np.testing.assert_array_equal(before['value'],after['value'][g,mapping])
        for k in ('target1','target2'):
            np.testing.assert_array_equal(after[k][g,mapping],mapping[g,before[k]])
        self.assertEqual(audit(after,*gold(after))['whole_graphs'],batch)
        again,m2=relayout(after,6,1,341);mcomp=m2[g,mapping]
        for k in ('target1','target2'):
            np.testing.assert_array_equal(again[k][g,mcomp],mcomp[g,before[k]])

    def test_wrong_parent_with_correct_colliding_value(self):
        d=dataset(2,2,3,1,776);p1,p2,orig,pv,out=gold(d)
        # Find two *generated slots* in the same Cell holding the same value.
        # If necessary set every payload equal; the original-coordinate task is unchanged.
        d['value'].fill(2);pv.fill(2);out.fill(2)
        query=int(np.flatnonzero(p2[0]==0)[0]);p2[0,query]=1
        r=audit(d,p1,p2,orig,pv,out)['run2']
        self.assertEqual((r['complete_graphs'],r['wrong_port_right_cell'],r['wrong_parent_value_looks_right']),(0,1,1))
        self.assertEqual((r['wrong_cell'],r['duplicates'],r['missing']),(0,1,1))
        self.assertEqual(r['parent_ready_obligations'],12)

    def test_wrong_origin_or_parent_cannot_be_repaired_downstream(self):
        d=dataset(2,2,2,1,24);p1,p2,origin,pv,out=gold(d)
        slot=3;origin[0,slot,2]=3
        r=audit(d,p1,p2,origin,pv,out)
        self.assertEqual(r['run1']['pointer_correct'],8);self.assertEqual(r['run1']['correct'],7)
        self.assertEqual(r['run2']['unavailable_required_parents'],1);self.assertEqual(r['run2']['correct'],7)
        p2[0,0]=-1
        self.assertEqual(audit(d,p1,p2,origin,pv,out)['run2']['invalid_pointer'],1)
        with self.assertRaises(ValueError):
            audit(d,p1,p2,origin.astype(float)+0.5,pv,out)

    def test_corrupt_truth_and_invalid_relayout_fail(self):
        d=dataset(1,1,1,1,12);self.assertEqual(audit(d,*gold(d))['whole_graphs'],1)
        with self.assertRaises(ValueError):relayout(d,2,1,14)
        d=dataset(2,2,2,1,24);expected=gold(d);d['target2'][0,0]^=1
        with self.assertRaisesRegex(ValueError,'labels disagree'):audit(d,*expected)
        with self.assertRaisesRegex(ValueError,'old labels'):relayout(d,1,4,1)


if __name__=='__main__':unittest.main()

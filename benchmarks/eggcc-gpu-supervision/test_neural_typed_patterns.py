import unittest
import numpy as np
from neural_typed_patterns import partitions,typed_snapshots,typed_candidates
from neural_snapshot_candidates import import_interfaces,binding_key
from reference_union_family import Reference
import test_neural_candidate_training as fixtures


class TypedPatterns(unittest.TestCase):
    def test_bell_counts_and_unique_canonical_names(self):
        for n,count in enumerate((1,1,2,5,15,52,203,877)):
            items=list(partitions(n))
            self.assertEqual(len(items),count)
            self.assertEqual(len(set(items)),count)
            for values in items:
                for i,v in enumerate(values):self.assertLessEqual(v,1+max(values[:i],default=-1))

    def test_capacity_is_explicit_not_silent_truncation(self):
        recipe=fixtures.PooledTraining().family();rule=recipe['rules'][0]
        with self.assertRaisesRegex(ValueError,'coverage is unresolved'):
            next(typed_snapshots(recipe,rule,0,pattern_limit=14))

    def test_canonical_patterns_match_independent_oracle(self):
        recipe=fixtures.PooledTraining().family(); rule=recipe['rules'][0]
        snapshots=list(typed_snapshots(recipe,rule,0))
        self.assertEqual(len(snapshots),15)
        labels=[]
        for snapshot in snapshots:
            rows,ids,*_=import_interfaces(recipe,snapshot)
            # Candidate query occurrences can reference a deduplicated same row.
            chosen=[rows.index(row) for row in snapshot['rows']]
            key=binding_key(rule,chosen,rows,ids)
            reference=Reference(recipe,rows,ids)
            expected={tuple(sorted(b.items())) for b in reference.matches(rule)}
            self.assertEqual(key is not None,key in expected)
            labels.append(key is not None)
        self.assertIn(True,labels);self.assertIn(False,labels)

    def test_semantic_targets_include_new_constructor_aliases(self):
        from test_neural_cell_chains import recipe
        data,_=typed_candidates(recipe(),(0,),eq_targets=True)
        self.assertEqual(len(data['valid']),2)
        self.assertTrue(data['eq_mask'].all())
        self.assertEqual(set(map(tuple,data['eq_target'])),{(0.,0.,0.),(1.,1.,1.)})
        plain,_=typed_candidates(recipe(),(0,))
        for k in plain:np.testing.assert_array_equal(data[k],plain[k])

    def test_enumeration_keeps_both_labels_and_deduplicates(self):
        data,coverage=typed_candidates(fixtures.PooledTraining().family(),(0,3))
        self.assertEqual(coverage[0]['enumerated_patterns_with_scalar_variants'],30)
        self.assertLess(len(data['valid']),30)
        self.assertEqual(set(data['valid']),{0,1})
        n=data['relations'].shape[-1]//2
        actual,required=data['relations'][:,:n],data['relations'][:,n:]
        np.testing.assert_array_equal(np.all((required==0)|(actual>0),axis=1),data['valid'])


if __name__=='__main__':unittest.main()

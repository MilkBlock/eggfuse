import unittest
import numpy as np
from select_eq_readout import fit_candidates,select,ALPHAS,query_location
from whole_cell_ridge import train

class ReadoutSelection(unittest.TestCase):
    def test_policies_use_declared_validation_metrics(self):
        rows=[dict(oracle_mse=.1,macro_exact_rate=.6,macro_false_pair_rate=.02),
              dict(oracle_mse=.2,macro_exact_rate=.8,macro_false_pair_rate=.03),
              dict(oracle_mse=.3,macro_exact_rate=.5,macro_false_pair_rate=.01)]
        self.assertEqual(select(rows),dict(mse=0,partition=1,false_merge=2))
        self.assertEqual(select([rows[0],rows[0]]),dict(mse=0,partition=0,false_merge=0))

    def test_unstable_candidate_cannot_win_and_empty_eligibility_fails(self):
        rows=[dict(oracle_mse=0,macro_exact_rate=1,macro_false_pair_rate=0,numerically_eligible=False),
              dict(oracle_mse=1,macro_exact_rate=.5,macro_false_pair_rate=.2,numerically_eligible=True)]
        self.assertEqual(select(rows),dict(mse=1,partition=1,false_merge=1))
        rows[1]['numerically_eligible']=False
        with self.assertRaisesRegex(ValueError,'no numerically eligible'):select(rows)

    def test_diagnostic_query_maps_through_quotient_layout(self):
        rows=[dict(run=2,ordinal=3,rule=4,pairs=[(0,1),(0,2),(1,2)],quotient=dict(representatives=np.array([1]))),
              dict(run=5,ordinal=6,rule=7,pairs=[(3,4)],quotient=dict(representatives=np.array([0])))]
        self.assertEqual(query_location(rows,0),dict(run=2,binding=3,rule=4,slots=[0,2]))
        self.assertEqual(query_location(rows,1),dict(run=5,binding=6,rule=7,slots=[3,4]))
        with self.assertRaises(ValueError):query_location(rows,2)

    def test_candidate_fit_matches_existing_ridge_without_validation_leakage(self):
        rng=np.random.default_rng(41);x=np.column_stack([np.ones(50),rng.normal(size=(50,7))]);y=rng.integers(0,2,50).astype(np.float32)
        mask=np.arange(50)<35
        candidates=fit_candidates(x[mask],y[mask]);coef,report=train(x,y[:,None],mask,~mask)
        i=ALPHAS.index(report['alpha'])
        np.testing.assert_allclose(candidates[:,i],coef[:,0],atol=1e-7,rtol=1e-6)
        # The fitting helper has no validation inputs; changing them leaves fits identical.
        y[~mask]=1-y[~mask]
        np.testing.assert_array_equal(candidates,fit_candidates(x[mask],y[mask]))

if __name__=='__main__':unittest.main()

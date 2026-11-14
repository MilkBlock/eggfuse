import unittest
from copy import deepcopy
import numpy as np
from condition_boundary import gate,fold
from test_device_query_join import fixture


class ConditionBoundary(unittest.TestCase):
    def test_fold_preserves_explicit_conditioned_linear_map(self):
        rng=np.random.default_rng(19);x=rng.normal(size=(7,9)).astype(np.float32)
        g=rng.normal(size=4).astype(np.float32);coef=rng.normal(size=(13,3)).astype(np.float32)
        expanded=np.concatenate([x,x[:,5:]*g],axis=1)
        np.testing.assert_allclose(x@fold(coef,g,5),expanded@coef,atol=2e-6)
        with self.assertRaises(ValueError):fold(coef[:-1],g,5)

    def test_gate_does_not_depend_on_rule_identifier_or_metadata(self):
        recipe,_=fixture();r=recipe['rules'][2];other=deepcopy(r)
        other['metadata']=dict(name='renamed',source_set='other stage');other['id']=999
        np.testing.assert_array_equal(gate(r,4),gate(other,4))
        np.testing.assert_array_equal(gate(r,4).reshape(2,4,32)[:,3],0)
        with self.assertRaises(ValueError):gate(r,1)

if __name__=='__main__':unittest.main()

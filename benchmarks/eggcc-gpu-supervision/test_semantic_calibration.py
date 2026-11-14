import unittest
import numpy as np
from calibrate_semantic_family import corrected,semantic_family


class Calibration(unittest.TestCase):
    def test_residual_is_folded_and_bias_unpenalized(self):
        x=np.ones((4,3),np.float32);y=np.array([[.1],[.2],[.3],[.4]],np.float32)
        base=np.full((3,1),.7,np.float32)
        coef=corrected(x,y,base,10.)
        self.assertEqual(coef.shape,base.shape)
        np.testing.assert_allclose(x@coef,np.broadcast_to(y.mean(0),y.shape),atol=2e-6)
        np.testing.assert_array_equal(base,np.full((3,1),.7,np.float32))

    def test_invalid_regularization_or_missing_bias_column_rejected(self):
        for alpha in (0.,-1.,float('nan')):
            with self.assertRaises(ValueError):corrected(np.ones((2,2)),np.ones((2,1)),np.zeros((2,1)),alpha)
        with self.assertRaises(ValueError):corrected(np.zeros((2,2)),np.ones((2,1)),np.zeros((2,1)),1.)

    def test_scope_uses_original_semantics_not_seed_templates_or_metadata(self):
        rule=dict(slots=[{'sort':'E'}],query=[],effects=[],metadata={'name':'ignored'})
        meta=dict(source_rules=[290],semantic_recipe=dict(rules=[rule,dict(slots=[],query=[],effects=[])]))
        self.assertEqual(semantic_family(meta),[{k:rule[k] for k in ('slots','query','effects')}])

if __name__=='__main__':unittest.main()

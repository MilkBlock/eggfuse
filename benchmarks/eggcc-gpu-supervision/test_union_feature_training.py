import unittest,json
import numpy as np
from fit_union_input_relations import fit
from collect_union_corpus import boundary


class UnionFeatureTraining(unittest.TestCase):
    def test_dual_ridge_matches_primal_with_unpenalized_intercept(self):
        rng=np.random.default_rng(9);x=rng.normal(size=(8,13)).astype(np.float32);x[:,0]=1
        y=rng.normal(size=(8,3)).astype(np.float32);alpha=10.
        coef,bias=fit(x,y,alpha)
        mean=x.mean(0);scale=np.maximum(x.std(0),.02);z=(x-mean)/scale
        expected=np.linalg.solve(z.T@z+alpha*np.eye(x.shape[1]),z.T@(y-y.mean(0)))
        np.testing.assert_allclose(x@coef+bias,z@expected+y.mean(0),atol=2e-6)
        self.assertTrue(np.isfinite(coef).all())

    def test_constant_input_predicts_training_mean(self):
        x=np.ones((3,4),np.float32);y=np.array([[1,2],[4,8],[7,2]],np.float32)
        coef,bias=fit(x,y,1.)
        np.testing.assert_allclose(x@coef+bias,np.broadcast_to(y.mean(0),y.shape))

    def test_folding_keeps_one_matmul_and_checks_template(self):
        from audit_union_family import fold_adapter
        rng=np.random.default_rng(4);coef=rng.normal(size=(5,3)).astype(np.float32)
        delta=rng.normal(size=coef.shape).astype(np.float32);bias=np.ones(3,np.float32)
        a=dict(parent_model_sha256='parent',rule_json=json.dumps({'effects':[]}),
            **{'base_inputs_1.0_coef':delta,'base_inputs_1.0_bias':bias})
        result=fold_adapter(dict(coef=coef),{'effects':[]},'parent',a)
        x=rng.normal(size=(2,5)).astype(np.float32);x[:,0]=1
        np.testing.assert_allclose(x@result['coef'],x@coef+x@delta+bias,atol=2e-6)
        with self.assertRaises(ValueError):fold_adapter(dict(coef=coef),{'effects':[1]},'parent',a)
        with self.assertRaises(ValueError):fold_adapter(dict(coef=coef),{'effects':[]},'other',a)

    def test_boundary_uses_pre_run_union_operands_and_copy_alias(self):
        rule=dict(effects=[dict(kind='copy',arg=dict(slot=0),dst=2),dict(kind='union',args=[dict(slot=2),dict(slot=1)])])
        def run(i,a,b):return dict(ordinal=i,audit=dict(bindings=[dict(rule=0,eq_ports=[dict(slot=0,before=a),dict(slot=1,before=b)])]))
        trace=dict(recipe=dict(rules=[rule]),runs=[run(4,'a','a'),run(7,'a','b')])
        self.assertEqual(boundary(trace,0),6)
        trace['runs']=trace['runs'][:1];self.assertIsNone(boundary(trace,0))

if __name__=='__main__':unittest.main()

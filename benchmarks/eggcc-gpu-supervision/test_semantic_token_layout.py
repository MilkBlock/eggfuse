import unittest
from copy import deepcopy
import numpy as np
import mlx.core as mx
from test_lower_constructor_sets import ConstructorSets
from lower_constructor_sets import lower
from device_semantic_template import template,neighborhood_template,token_required,semantic
from device_input_features import compile_inputs,encode_inputs
from device_token_refresh import encode_batch
from label_composed_witnesses import resolve_identities,target
from reference_union_family import Reference


class SemanticTokenLayout(unittest.TestCase):
    def fixture(self):
        recipe,rows,ids=ConstructorSets().fixture(False)
        lowered,_=lower(recipe)
        return recipe,lowered,rows,ids

    def test_compiler_temporary_reuses_semantic_role_and_does_not_change_request(self):
        recipe,new,_,_=self.fixture();a=recipe['rules'][0];b=new['rules'][0]
        for f in (template,neighborhood_template):
            ra,qa=f(a);rb,qb=f(b)
            np.testing.assert_array_equal(qa,qb);np.testing.assert_array_equal(rb[:2],ra)
            np.testing.assert_array_equal(rb[2],ra[1])
        self.assertEqual(token_required(b).tolist(),[True,True,False])
        bad=deepcopy(b);bad['effects']=bad['effects'][:1]
        with self.assertRaisesRegex(ValueError,'unproved'):semantic(bad)
        bad=deepcopy(b);bad['effects'].append(deepcopy(bad['effects'][-1]))
        with self.assertRaisesRegex(ValueError,'uncovered'):semantic(bad)

    def test_input_and_completed_token_invariant_under_lowering_on_gpu(self):
        recipe,new,_,_=self.fixture();layouts=[compile_inputs(r) for r in (recipe['rules'][0],new['rules'][0])]
        tokens=[];features=[]
        for r,layout in zip((recipe['rules'][0],new['rules'][0]),layouts):
            n=len(r['slots']);roots=np.array([[1,2,2][:n]],np.int32)
            x=dict(roots=roots,valid=np.ones((1,n),bool),numbers=np.zeros((1,n),np.float32),numeric=np.zeros((1,n),bool),scalar_codes=np.zeros((1,n,64),np.float32),scalar_valid=np.zeros((1,n),bool))
            features.append(encode_inputs(x,layout,np)[0])
            dev=lambda v:mx.array(v)
            token=encode_batch(dev(roots),dev(layout['sorts']),dev(layout['eq']),dev(token_required(r)[None]),dev(layout['roles'][:,:,:64]),dev(x['scalar_codes']),mx)
            mx.eval(token);tokens.append(np.array(token))
        for k in features[0]:np.testing.assert_array_equal(features[0][k],features[1][k])
        np.testing.assert_allclose(tokens[0],tokens[1],atol=2e-6)

    def test_cpu_labels_resolve_actual_foreign_ids_and_omit_temporaries(self):
        recipe,new,rows,ids=self.fixture();ref=Reference(recipe,rows,ids);ref.saturate(recipe['rules'])
        mapping=resolve_identities(ref,[('F',(0,),99)],len(ids))
        self.assertEqual(mapping[99],1)
        with self.assertRaisesRegex(ValueError,'absent'):resolve_identities(ref,[('Unknown',(0,),99)],len(ids))
        value,labels=target(new['rules'][0],np.array([0,1,-1]),mapping,ref,{},3)
        self.assertEqual(labels.tolist(),[0,1,-1]);self.assertTrue(np.isfinite(value).all())

if __name__=='__main__':unittest.main()

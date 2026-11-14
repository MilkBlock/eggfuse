import unittest
import numpy as np
import mlx.core as mx
import mlx.nn as nn
from mlx.utils import tree_flatten
from test_neural_cell_chains import recipe
from train_neural_owner_blocks import build
from neural_owner_blocks import OwnerBlocks,replay
from neural_proof_token import enrich


class ProofTokenTests(unittest.TestCase):
    def test_target_residual_preserves_source_and_receives_gradients(self):
        base,chain,_=build(recipe(),2,23)
        p={k:mx.array(v[chain['parent']]) for k,v in base.items()};c={k:mx.array(v) for k,v in chain.items()}
        m=OwnerBlocks(base['x'].shape[-1],base['relations'].shape[-1],3,proof_token=True)
        m.immutable_source=True;m.cell.freeze();m.eq.freeze();m.cross.freeze();m.update_source.freeze()
        _,source=m.cell(p['x'],p['edges'],p['mask'],p['request'],p['relations'])
        first=replay(m,p,c)
        np.testing.assert_array_equal(first[2][:,0],source)
        m.proof_target.weight=mx.ones_like(m.proof_target.weight)*.01
        changed=replay(m,p,c)
        np.testing.assert_array_equal(changed[2][:,0],source)
        self.assertFalse(np.allclose(first[2][:,1],changed[2][:,1]))
        poisoned=dict(c,eq_target=1-c['eq_target'],source_target=c['source_target']+99,cross_eq_target=1-c['cross_eq_target'])
        np.testing.assert_array_equal(replay(m,p,poisoned)[2],changed[2])
        _,g=nn.value_and_grad(m,lambda x:mx.mean(replay(x,p,c)[2][:,1]**2))(m);mx.eval(g)
        flat=dict(tree_flatten(g));self.assertEqual(set(flat),{'proof_target.weight'})
        self.assertTrue(np.any(np.array(flat['proof_target.weight'])!=0))

    def test_saved_replay_enrichment_and_actual_third_consumer(self):
        from neural_third_step import build as build_third,replay_blocks
        raw,_=build_third(recipe(),1,23,per_pair=1,context_capacity=4,block_owner=True)
        _,catalog,_=build(recipe(),1,23)
        old={k:v for k,v in raw.items() if k!='c_owner_proof_code'}
        restored=enrich(old,catalog)
        np.testing.assert_array_equal(restored['c_owner_proof_code'],raw['c_owner_proof_code'])
        altered=dict(catalog,source_eq_target=1-catalog['source_eq_target'],cross_eq_target=1-catalog['cross_eq_target'])
        np.testing.assert_array_equal(enrich(old,altered)['c_owner_proof_code'],raw['c_owner_proof_code'])
        data={k:mx.array(v) for k,v in raw.items()}
        m=OwnerBlocks(raw['p_x'].shape[-1],raw['relations'].shape[-1],3,proof_token=True);m.immutable_source=True
        before=replay_blocks(m,data)[1]
        m.proof_target.weight=mx.random.normal(m.proof_target.weight.shape)*.1
        after=replay_blocks(m,data)[1]
        self.assertFalse(np.allclose(before,after))


if __name__=='__main__':unittest.main()

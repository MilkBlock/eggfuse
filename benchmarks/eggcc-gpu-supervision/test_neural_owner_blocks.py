import unittest
import numpy as np
import mlx.core as mx
import mlx.nn as nn
from mlx.utils import tree_flatten
from test_neural_cell_chains import recipe
from train_neural_owner_blocks import build,objective
from neural_owner_blocks import OwnerBlocks,replay,joint_arrays


class OwnerBlockTests(unittest.TestCase):
    def test_source_residual_and_teacher_free_gpu_replay(self):
        base,chain,_=build(recipe(),4,23)
        b={k:mx.array(v[chain['parent']]) for k,v in base.items()};c={k:mx.array(v) for k,v in chain.items()}
        model=OwnerBlocks(base['x'].shape[-1],base['relations'].shape[-1],3)
        _,source=model.cell(b['x'],b['edges'],b['mask'],b['request'],b['relations'])
        _,_,blocks=mx.compile(lambda p,q:replay(model,p,q))(b,c);mx.eval(blocks)
        np.testing.assert_allclose(blocks[:,0],source,atol=1e-6)
        changed=dict(c,tokens=c['tokens']+999,source_target=c['source_target']+999,cross_eq_target=1-c['cross_eq_target'])
        for a,z in zip(replay(model,b,c),replay(model,b,changed)):np.testing.assert_array_equal(a,z)
        value,g=nn.value_and_grad(model,objective)(model,b,b,c);mx.eval(value,g)
        flat=dict(tree_flatten(g))
        for prefix in ('update_source.','cross.','cell.encode.'):
            self.assertTrue(any(k.startswith(prefix) and np.any(np.abs(np.array(v))>1e-8) for k,v in flat.items()),prefix)

    def test_immutable_mode_skips_source_and_cross_networks(self):
        base,chain,_=build(recipe(),1,23)
        b={k:mx.array(v[chain['parent']]) for k,v in base.items()};c={k:mx.array(v) for k,v in chain.items()}
        model=OwnerBlocks(base['x'].shape[-1],base['relations'].shape[-1],3)
        model.immutable_source=True
        model.update_source.layers[-1].bias=mx.full((128,),float('nan'))
        model.cross.layers[-1].bias=mx.full((9,),float('nan'))
        _,source=model.cell(b['x'],b['edges'],b['mask'],b['request'],b['relations'])
        _,_,blocks=replay(model,b,c)
        scores=model.readout(blocks,c['source_request'],c['request'],c['owner_request'],include_cross=False)
        mx.eval(blocks,scores)
        np.testing.assert_array_equal(blocks[:,0],source)
        self.assertTrue(all(np.isfinite(np.array(v)).all() for v in scores))
        np.testing.assert_array_equal(scores[2],-np.ones((len(chain['valid']),9)))

    def test_joint_audit_detects_cross_block_false_merge(self):
        from neural_eq_readout import metrics
        source=np.array([[-1.]],np.float32);target=source.copy();cross=np.array([[1.,-1.,-1.,1.]],np.float32)
        joint=joint_arrays(source,target,cross,2);truth=(joint>0).astype(np.float32);mask=np.ones_like(truth,bool)
        self.assertEqual(metrics(joint,truth,mask,4)['closed_exact_states'],1)
        bad=joint_arrays(source,target,np.ones_like(cross),2)
        self.assertEqual(metrics(bad,truth,mask,4)['states_with_false_merge'],1)


if __name__=='__main__':unittest.main()

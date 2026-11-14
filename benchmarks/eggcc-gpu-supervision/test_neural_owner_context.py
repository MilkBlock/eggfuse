import unittest
import numpy as np
import mlx.core as mx
import mlx.nn as nn
from mlx.utils import tree_flatten
from neural_owner_context import encode,replay_features
from neural_owner_blocks import OwnerBlocks


class OwnerContextTests(unittest.TestCase):
    def test_directory_replay_parity_and_handle_renaming(self):
        kind=np.array([[1,2,0,1]],np.int32);mask=np.array([[1,1,1,0]],bool)
        code=np.linspace(-1,1,64,dtype=np.float32)[None,:]
        batch=dict(source_kind=kind,mask=mask,c_owner_request=code)
        owners=np.array([[13,13,8,13]]);blocks=np.array([[0,1,0,0]])
        codes=np.broadcast_to(code[:,None,:],(1,4,64));owned=kind>0
        expected=replay_features(batch,np)
        actual=encode(owners,blocks,codes,owned,mask,np)
        np.testing.assert_array_equal(actual,expected)
        np.testing.assert_array_equal(actual,encode(owners*31+7,blocks,codes,owned,mask,np))
        np.testing.assert_allclose(actual,encode(*[mx.array(x) for x in (owners,blocks,codes,owned,mask)],mx),atol=1e-6)
        split=owners.copy();split[0,1]=14
        self.assertTrue(np.all(encode(split,blocks,codes,owned,mask,np)[0,0,1]==0))
        self.assertTrue(np.all(actual[0,2:]==0));self.assertTrue(np.all(actual[0,:,2:]==0))

    def test_zero_adapter_parity_and_only_adapter_gradient(self):
        mx.random.seed(43)
        model=OwnerBlocks(64,8,3,owner_aware=True)
        model.cell.freeze();model.eq.freeze();model.update_source.freeze();model.cross.freeze()
        args=(mx.random.normal((2,2,128)),mx.random.normal((2,2,2,64)),mx.ones((2,2),mx.bool_),mx.random.normal((2,64)),mx.ones((2,8)))
        features=mx.random.normal((2,2,2,64))
        for a,b in zip(model.cell.transition(*args),model.consume(*args,features)):
            np.testing.assert_array_equal(a,b)
        def loss(m):return mx.sum(m.consume(*args,features)[1]**2)
        value,grad=nn.value_and_grad(model,loss)(model);mx.eval(value,grad)
        flat=dict(tree_flatten(grad));self.assertEqual(set(flat),{'owner_edges.weight'})
        self.assertTrue(np.any(np.abs(np.array(flat['owner_edges.weight']))>1e-8))


if __name__=='__main__':unittest.main()

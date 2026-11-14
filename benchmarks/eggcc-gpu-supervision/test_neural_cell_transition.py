import unittest
import numpy as np
import mlx.core as mx
import mlx.nn as nn
from neural_cell_transition import CellTransition,loss

class NeuralCell(unittest.TestCase):
    def batch(self):
        mx.random.seed(12)
        return dict(source_target=mx.random.normal((4,3,128)),x=mx.random.normal((4,3,16)),edges=mx.random.normal((4,3,3,64)),mask=mx.array([[True,True,False]]*4),request=mx.random.normal((4,64)),valid=mx.array([0.,1.,0.,1.]),target=mx.random.normal((4,128)))

    def test_source_permutation_and_padding(self):
        b=self.batch();model=CellTransition(16,32)
        expected=model(b['x'],b['edges'],b['mask'],b['request'])
        p=mx.array([1,0,2]);actual=model(b['x'][:,p],b['edges'][:,p][:,:,p],b['mask'][:,p],b['request']);mx.eval(expected,actual)
        for x,y in zip(expected,actual):np.testing.assert_allclose(x,y,atol=2e-6)
        x=mx.where(b['mask'][...,None],b['x'],100.)
        edge_valid=b['mask'][:,:,None]&b['mask'][:,None,:]
        edge=mx.where(edge_valid[...,None],b['edges'],-100.)
        actual=model(x,edge,b['mask'],b['request']);mx.eval(actual)
        for x,y in zip(expected,actual):np.testing.assert_allclose(x,y,atol=2e-6)

    def test_generated_tokens_enter_same_transition_without_field_encoding(self):
        b=self.batch();model=CellTransition(16,32)
        sources=model.encode(b['x']);first=model.transition(sources,b['edges'],b['mask'],b['request'])
        incoming=mx.concatenate([first[1][:,None,:],sources[:,1:]],axis=1)
        second=model.transition(incoming,b['edges'],b['mask'],b['request']);mx.eval(second)
        self.assertEqual(second[1].shape,(4,128))
        self.assertTrue(np.isfinite(np.array(second[1])).all())

    def test_all_prediction_components_receive_gradients(self):
        b=self.batch();model=CellTransition(16,32);value,g=nn.value_and_grad(model,loss)(model,b);mx.eval(value,g)
        from mlx.utils import tree_flatten
        values=dict(tree_flatten(g))
        for prefix in ('encode','edge_score','edge_value','accept','successor'):
            self.assertTrue(any(name.startswith(prefix) and np.any(np.abs(np.array(v))>1e-8) for name,v in values.items()),prefix)
        self.assertTrue(np.isfinite(float(value)))

if __name__=='__main__':unittest.main()

import unittest
import numpy as np
import mlx.core as mx
import mlx.nn as nn
from neural_ordered_relations import demand,incidence,projected,OrderedCellTransition
from neural_cell_transition import CellTransition,loss
from neural_cell_samples import samples
from train_neural_cell_chains import build,rollout
import test_neural_candidate_training as pooled_test


class OrderedRelations(unittest.TestCase):
    def test_actual_ports_are_ordered_and_identity_magnitudes_irrelevant(self):
        r=pooled_test.PooledTraining().family()['rules'][0]; required=demand(r,2,2)
        a=np.array([[[0,1],[1,2]]]); wrong=np.array([[[0,1],[2,1]]])
        ea=incidence(a,required); eb=incidence(wrong,required)
        self.assertEqual(ea[:,:16].sum(),eb[:,:16].sum())
        self.assertFalse(np.array_equal(ea,eb))
        np.testing.assert_array_equal(ea,incidence(np.array([[[70,91],[91,4]]]),required))
        np.testing.assert_array_equal(ea,incidence(mx.array(a),mx.array(required),mx))

    def test_generated_chain_includes_actual_negative_interfaces(self):
        recipe=pooled_test.PooledTraining().family()
        rule=recipe['rules'][0]
        rule['slots'].append(dict(sort=recipe['tables'][0]['schema'][0],definition=0))
        rule['effects']=[dict(kind='construct',call=dict(table='F'),args=[dict(slot=2)],dst=3)]
        base,chain,_=build(recipe,4,23,ordered=True)
        n=chain['relations'].shape[-1]//2
        actual=chain['relations'][:,:n]; required=chain['relations'][:,n:]
        proves=np.all((required==0)|(actual>0),axis=1)
        np.testing.assert_array_equal(proves,chain['valid'])
        self.assertIn('relations',base)
        parent={k:mx.array(v[chain['parent']]) for k,v in base.items()}
        device={k:mx.array(v) for k,v in chain.items()}
        model=OrderedCellTransition(base['x'].shape[-1],base['relations'].shape[-1],32)
        def second_only(m):return mx.mean(rollout(m,parent,device)[2]**2)
        _,g=nn.value_and_grad(model,second_only)(model);mx.eval(g)
        from mlx.utils import tree_flatten
        self.assertTrue(any(k.startswith('encode') and np.any(np.abs(np.array(v))>1e-8) for k,v in tree_flatten(g)))
        # This check audits the feature builder; the model is not given proves.

    def test_zero_initialized_correction_preserves_parent_and_trains(self):
        data=samples(pooled_test.PooledTraining().family(),4,23,ordered=True)
        b={k:mx.array(v) for k,v in data.items()}
        mx.random.seed(11); parent=CellTransition(b['x'].shape[-1],32)
        model=OrderedCellTransition(b['x'].shape[-1],b['relations'].shape[-1],32)
        model.update(parent.parameters())
        a=parent(b['x'],b['edges'],b['mask'],b['request'])
        c=model(b['x'],b['edges'],b['mask'],b['request'],b['relations'])
        for x,y in zip(a,c):np.testing.assert_array_equal(x,y)
        _,grad=nn.value_and_grad(model,loss)(model,b); mx.eval(grad)
        self.assertTrue(np.any(np.array(grad['match_relation']['weight'])!=0))
        self.assertTrue(np.any(np.array(grad['token_relation']['weight'])!=0))


if __name__=='__main__':unittest.main()

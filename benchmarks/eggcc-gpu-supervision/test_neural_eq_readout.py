import unittest
import numpy as np
import mlx.core as mx
import mlx.nn as nn
from mlx.utils import tree_flatten
from neural_eq_readout import targets,metrics,masked_loss
from neural_cell_samples import samples,apply_instance
from neural_cell_chains import completed
from train_neural_eq_readout import CompletionReadout
from reference_union_family import Reference
from device_snapshot_import import identity
from test_neural_cell_chains import recipe


class SemanticReadout(unittest.TestCase):
    def test_labels_capture_constructor_reuse_beyond_query(self):
        r=recipe();ids={identity(dict(sort='E',eq=str(i))):i for i in range(2)}
        ref=Reference(r,[],ids);ref.construct('F',[0],1);ref.construct('F',[1],0)
        binding={0:0,1:1};apply_instance(ref,r['rules'][0],binding)
        values=completed(r['rules'][0],binding,ref)
        target=targets(r['rules'][0],values,ref,3)
        np.testing.assert_array_equal(target['eq_target'],[0,1,0])
        self.assertTrue(target['eq_mask'].all())
        local=Reference(r,[],ids);local.construct('F',[0],1)
        local_binding={0:0,1:1};apply_instance(local,r['rules'][0],local_binding)
        local_target=targets(r['rules'][0],completed(r['rules'][0],local_binding,local),local,3)
        np.testing.assert_array_equal(local_target['eq_target'],[0,0,0])

    def test_closure_distinguishes_missing_edge_from_false_merge(self):
        logits=np.array([[1,-1,1],[1,-1,1]])
        labels=np.array([[1,1,1],[1,0,0]])
        m=metrics(logits,labels,np.ones((2,3),bool),3)
        self.assertEqual(m['false_negative_pairs'],1)
        self.assertEqual(m['closed_false_negative_pairs'],0)
        self.assertEqual(m['closed_false_positive_pairs'],2)
        self.assertEqual(m['closed_exact_states'],1)
        self.assertEqual(m['states_with_false_merge'],1)

    def test_semantic_loss_reaches_encoder_with_interface_head_frozen(self):
        mx.random.seed(131);data=samples(recipe(),4,23,ordered=True,eq_targets=True);batch={k:mx.array(v) for k,v in data.items()}
        model=CompletionReadout(data['x'].shape[-1],data['relations'].shape[-1],3)
        def objective(m):
            _,token=m.cell(batch['x'],batch['edges'],batch['mask'],batch['request'],batch['relations'])
            return masked_loss(m.eq(token,batch['request']),batch['eq_target'],batch['eq_mask'])
        _,g=nn.value_and_grad(model,objective)(model);mx.eval(g)
        gradients=dict(tree_flatten(g))
        self.assertTrue(any(k.startswith('cell.encode') and np.any(np.abs(np.array(v))>1e-8) for k,v in gradients.items()))
        self.assertFalse(any(k.startswith(('cell.relation.','cell.match_relation.')) for k in gradients))
        self.assertTrue(any(k.startswith('eq.layers') and np.any(np.abs(np.array(v))>1e-8) for k,v in gradients.items()))


if __name__=='__main__':unittest.main()

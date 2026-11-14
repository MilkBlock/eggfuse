import unittest
import numpy as np
import mlx.core as mx
import mlx.nn as nn
from mlx.utils import tree_flatten
from neural_third_step import replay,valid_candidate
from neural_ordered_relations import ordered_model
from neural_cell_samples import samples
from neural_cell_chains import chains
from test_neural_cell_chains import recipe


class ThirdStep(unittest.TestCase):
    def test_current_state_samples_have_no_recurrent_inputs(self):
        from neural_third_step import build
        from train_current_cell import CurrentCellModel
        raw,report=build(recipe(),1,23,per_pair=1,current_state=True,include_uncovered_transfers=True)
        self.assertTrue(report['current_state_inputs'])
        self.assertFalse(report['recurrent_latent_inputs'])
        self.assertFalse(any(k.startswith(('p_', 'c_')) for k in raw))
        self.assertNotIn('seed_x',raw)
        data={k:mx.array(v) for k,v in raw.items()}
        model=CurrentCellModel(raw['x'].shape[-1],raw['relations'].shape[-1],3)
        before=model(data)
        after=model(dict(data,eq_target=1-data['eq_target'],source_kind=mx.zeros_like(data['source_kind'])))
        for a,b in zip(before,after):np.testing.assert_array_equal(a,b)

    def test_entry_limit_is_explicit(self):
        from neural_third_step import build
        with self.assertRaisesRegex(ValueError,"positive entry limit"):
            build(recipe(),1,23,entries_per_consumer=0)

    def test_block_replay_consumes_updated_source_and_has_no_label_input(self):
        from neural_third_step import build,replay_blocks
        from neural_owner_blocks import OwnerBlocks
        raw,report=build(recipe(),1,23,per_pair=1,context_capacity=4,block_owner=True)
        self.assertEqual(report['cases'],report['physical_transfers'])
        self.assertTrue(report['block_owner'])
        self.assertEqual(report['entries_per_consumer'],2)
        data={k:mx.array(v) for k,v in raw.items()}
        model=OwnerBlocks(raw['p_x'].shape[-1],raw['relations'].shape[-1],3)
        original=replay_blocks(model,data)
        changed=replay_blocks(model,dict(data,eq_target=1-data['eq_target']))
        for a,b in zip(original,changed):np.testing.assert_array_equal(a,b)
        # No teacher tokens are present; third-step gradients reach the source
        # residual through actual post-handoff source-kind selections.
        _,g=nn.value_and_grad(model,lambda m:mx.mean(replay_blocks(m,data)[1]**2))(model)
        mx.eval(g)
        self.assertTrue(any(k.startswith('update_source.') and np.any(np.abs(np.array(v))>1e-8) for k,v in tree_flatten(g)))
        model.update_source.layers[-1].bias=mx.ones(128)*0.5
        updated=replay_blocks(model,data)
        self.assertFalse(np.allclose(original[1],updated[1]))
        model.cell.freeze();model.eq.freeze()
        _,frozen_gradient=nn.value_and_grad(model,lambda m:mx.mean(m.eq(replay_blocks(m,data)[1],data['request'])**2))(model)
        mx.eval(frozen_gradient);flat=dict(tree_flatten(frozen_gradient))
        self.assertFalse(any(k.startswith(('cell.','eq.')) for k in flat))
        self.assertTrue(any(k.startswith('update_source.') and np.any(np.abs(np.array(v))>1e-8) for k,v in flat.items()))

    def test_key_membership_does_not_override_inconsistent_repeated_slot(self):
        key=((0,3),(1,4));expected={key}
        self.assertFalse(valid_candidate(np.array([1,0,1,1]),key,expected))
        self.assertTrue(valid_candidate(np.array([1,1,1,1]),key,expected))
        self.assertFalse(valid_candidate(np.array([1,1,1,1]),key,set()))

    def test_replay_uses_lineage_and_backpropagates_without_target_tokens(self):
        r=recipe();eq=r['tables'][0]['schema'][0]
        r['rules'][0]=dict(slots=[dict(sort=eq,definition='query' if i<3 else 0) for i in range(4)],
            query=[dict(call=dict(table='F'),args=[dict(slot=0),dict(slot=1)]),dict(call=dict(table='F'),args=[dict(slot=1),dict(slot=2)])],
            effects=[dict(kind='construct',call=dict(table='F'),args=[dict(slot=2)],dst=3)])
        records=[];base=samples(r,4,23,records,ordered=True);c,_=chains(r,records,ordered=True)
        i=int(np.flatnonzero(c['valid'])[0]);parent=int(c['parent'][i])
        data={'p_'+k:mx.array(base[k][parent:parent+1]) for k in ('x','edges','mask','request','relations')}
        data.update({'c_'+k:mx.array(c[k][i:i+1]) for k in ('seed_x','replace','edges','mask','request','relations')})
        data.update({k:mx.array(c[k][i:i+1]) for k in ('seed_x','edges','mask','request','relations')})
        data['mask']=mx.ones((1,2),mx.bool_);data['source_kind']=mx.array([[1,2]])
        mx.random.seed(71);model=ordered_model(base['x'].shape[-1],base['relations'].shape[-1],True)
        actual=replay(model,data);changed=replay(model,dict(data,eq_target=mx.ones((1,6)),seed_x=data['seed_x']+1000));mx.eval(actual,changed)
        # Neither seed encoding nor arbitrary labels may overwrite generated sources.
        for a,b in zip(actual,changed):np.testing.assert_array_equal(a,b)
        def objective(m):return mx.mean(replay(m,data)[1]**2)
        _,g=nn.value_and_grad(model,objective)(model);mx.eval(g)
        gradients=dict(tree_flatten(g))
        for prefix in ('encode.','successor.'):
            self.assertTrue(any(k.startswith(prefix) and np.any(np.abs(np.array(v))>1e-8) for k,v in gradients.items()))
        different=replay(model,dict(data,source_kind=mx.zeros((1,2),mx.int32)))
        self.assertFalse(np.allclose(actual[1],different[1]))
        # With only second-generation sources selected, p_x can influence the
        # loss solely through first -> second -> third, not a direct shortcut.
        def through_both(x):
            return mx.mean(replay(model,dict(data,p_x=x,source_kind=mx.full((1,2),2,mx.int32)))[1]**2)
        _,input_gradient=mx.value_and_grad(through_both)(data['p_x']);mx.eval(input_gradient)
        self.assertTrue(np.any(np.abs(np.array(input_gradient))>1e-8))


if __name__=='__main__':unittest.main()

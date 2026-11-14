import unittest
import numpy as np
import mlx.core as mx
import mlx.nn as nn
from mlx.utils import tree_flatten
from neural_cell_samples import samples,apply_instance
from neural_cell_chains import chains
from neural_cell_transition import CellTransition
from train_neural_cell_chains import rollout
from reference_union_family import Reference
from device_snapshot_import import identity


def recipe():
    eq=dict(kind='eq',name='E')
    rule=dict(slots=[dict(sort=eq,definition='query' if i<2 else 0) for i in range(3)],query=[dict(call=dict(table='F'),args=[dict(slot=0),dict(slot=1)])],effects=[dict(kind='construct',call=dict(table='F'),args=[dict(slot=1)],dst=2)])
    return dict(tables=[dict(name='F',kind='constructor',schema=[eq,eq])],rules=[rule])

class NeuralChains(unittest.TestCase):
    def test_instance_labels_do_not_apply_other_bindings(self):
        r=recipe();ids={identity(dict(sort='E',eq=str(i))):i for i in range(3)};ref=Reference(r,[],ids)
        ref.construct('F',[0],1);ref.construct('F',[1],2)
        apply_instance(ref,r['rules'][0],{0:0,1:1})
        self.assertEqual(len(ref.parent),3)
        self.assertNotIn(('F',(2,)),{(t,v[:-1]) for t,v in ref.facts})

    def test_union_only_producer_exposes_changed_interfaces(self):
        r=recipe();eq=r['tables'][0]['schema'][0]
        r['rules'][0]=dict(slots=[dict(sort=eq,definition='query') for _ in range(3)],query=[dict(call=dict(table='F'),args=[dict(slot=0),dict(slot=1)]),dict(call=dict(table='F'),args=[dict(slot=1),dict(slot=2)])],effects=[dict(kind='union',args=[dict(slot=0),dict(slot=2)])])
        records=[];samples(r,4,23,records)
        self.assertTrue(any(v['eq_changed'] for v in records))
        chain,coverage=chains(r,records)
        self.assertEqual(coverage['producers'],[0]);self.assertGreater(coverage['positive'],0)

    def test_multi_entry_negatives_retain_generated_source(self):
        r=recipe();eq=r['tables'][0]['schema'][0]
        r['rules'][0]=dict(slots=[dict(sort=eq,definition='query' if i<3 else 0) for i in range(4)],query=[dict(call=dict(table='F'),args=[dict(slot=0),dict(slot=1)]),dict(call=dict(table='F'),args=[dict(slot=1),dict(slot=2)])],effects=[dict(kind='construct',call=dict(table='F'),args=[dict(slot=2)],dst=3)])
        records=[];samples(r,4,23,records);chain,coverage=chains(r,records)
        self.assertGreater(coverage['positive'],0);self.assertEqual(coverage['positive'],coverage['negative'])
        self.assertTrue(chain['replace'].any(axis=1).all())
        self.assertFalse(chain['owner_covered'][~chain['valid']].any())
        np.testing.assert_array_equal(chain['target'][~chain['valid']],0)

    def test_effect_backed_sources_and_no_teacher_token_leak(self):
        records=[];base=samples(recipe(),4,23,records);chain,coverage=chains(recipe(),records)
        self.assertGreater(coverage['chains'],0);self.assertTrue(chain['replace'].all())
        np.testing.assert_allclose(chain['tokens'][:,0],base['target'][chain['parent']],atol=2e-6)
        parent={k:mx.array(v[chain['parent']]) for k,v in base.items()};c={k:mx.array(v) for k,v in chain.items()};model=CellTransition(base['x'].shape[-1],32)
        original=rollout(model,parent,c);changed=rollout(model,parent,dict(c,tokens=c['tokens']+100));mx.eval(original,changed)
        for x,y in zip(original,changed):np.testing.assert_array_equal(x,y)
        def second_only(m):return mx.mean(rollout(m,parent,c)[2]**2)
        _,g=nn.value_and_grad(model,second_only)(model);mx.eval(g)
        self.assertTrue(any(k.startswith('encode') and np.any(np.abs(np.array(v))>1e-8) for k,v in tree_flatten(g)))

if __name__=='__main__':unittest.main()

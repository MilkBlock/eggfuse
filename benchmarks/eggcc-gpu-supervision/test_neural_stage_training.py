import unittest
import numpy as np
from device_stage_models import select_ruleset
from neural_cell_samples import samples
from test_neural_cell_chains import recipe
from reference_union_family import Reference
from typed_literal import resolved


class StageTrainingTests(unittest.TestCase):
    def test_training_uses_declared_membership_and_local_ids(self):
        r=recipe();r['rules']=r['rules']*2
        r['rulesets']=[dict(name='combined',rule_ids=[1,0])]
        r['control']=dict(repeat=7,body=dict(run='combined'));r['sha256']='original';r['event_routes']=[dict(consumer=99)]
        local,manifest=select_ruleset(r,'combined')
        self.assertEqual(manifest['source_rule_ids'],[1,0])
        self.assertEqual(local['rulesets'],[dict(name='combined',rule_ids=[0,1])])
        self.assertEqual(local['control'],dict(run='combined'));self.assertNotIn('sha256',local);self.assertEqual(local['event_routes'],[])
        self.assertEqual(r['control']['repeat'],7)
        with self.assertRaises(ValueError):select_ruleset(r,'unknown')

    def test_literal_constructor_and_copy_targets_are_exact(self):
        r=recipe();eq=r['rules'][0]['slots'][0]['sort'];integer=dict(kind='i64',name='i64')
        lit=dict(sort=integer,literal=(1<<60)+7)
        r['tables'].append(dict(name='Int',kind='constructor',schema=[integer,eq]))
        rule=r['rules'][0];rule['slots']+=[dict(sort=integer,definition='effect'),dict(sort=eq,definition='effect')]
        rule['effects'] += [dict(kind='copy',arg=lit,dst=3),dict(kind='construct',call=dict(table='Int'),args=[lit],dst=4)]
        records=[];data=samples(r,4,13,records,ordered=True,eq_targets=True)
        self.assertTrue(np.isfinite(data['target']).all());self.assertEqual(len(records),4)
        for rec in records:
            ref=rec['reference'];before=len(ref.parent);address=resolved(lit,{},ref)
            self.assertEqual(ref.scalar_values[address]['value'],(1<<60)+7);self.assertEqual(len(ref.parent),before)
        # A literal export is a real fact, but has no source payload slot.
        # It must not acquire ownership coverage by pretending to be slot zero.
        from neural_cell_chains import chains
        consumer=dict(slots=[dict(sort=integer,definition='query'),dict(sort=eq,definition='query')],query=[dict(call=dict(table='Int'),args=[dict(slot=0),dict(slot=1)])],effects=[])
        r['rules'].append(consumer)
        chain,_=chains(r,records,ordered=True,eq_targets=True)
        used=(chain['consumer']==1)&chain['valid']
        self.assertTrue(used.any());self.assertFalse(chain['owner_covered'][used].any())
        empty=Reference(r,[],{})
        with self.assertRaisesRegex(ValueError,'absent'):resolved(lit,{},empty)
        self.assertEqual(len(empty.parent),0)


if __name__=='__main__':unittest.main()

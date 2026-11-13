import unittest,copy
import numpy as np
from device_snapshot_import import prepare,reference_keys,identity


def fixture():
    eq=dict(kind='eq',name='E');integer=dict(kind='i64',name='i64')
    rule=dict(metadata=dict(source_set='s'),slots=[dict(sort=s,definition='query') for s in (integer,eq)],query=[dict(call=dict(table='F'),args=[dict(slot=0),dict(slot=1)])],effects=[])
    recipe=dict(tables=[dict(name='F',kind='constructor',schema=[integer,eq])],rules=[rule])
    row=dict(table='F',subsumed=False,values=[dict(sort='i64',value=16777217),dict(sort='E',eq='Cell(9007199254740993)')])
    return recipe,dict(rows=[row])


class SnapshotImport(unittest.TestCase):
    def test_effect_tables_are_imported_and_hidden_reuse_is_not_assumed(self):
        recipe,snapshot=fixture();eq=dict(kind='eq',name='E')
        recipe['tables'].append(dict(name='G',kind='constructor',schema=[eq,eq]))
        recipe['rules'][0]['slots'].append(dict(sort=eq,definition='effect'))
        recipe['rules'][0]['effects']=[dict(kind='construct',call=dict(table='G'),args=[dict(slot=1)],dst=2)]
        snapshot['rows'].append(dict(table='G',subsumed=False,values=[snapshot['rows'][0]['values'][1],dict(sort='E',eq='Cell(7)')]))
        _,_,_,rows=prepare(recipe,snapshot,0,2,include_effects=True)
        self.assertEqual({r['table'] for r in rows},{'F','G'})
        snapshot['rows'][1]['subsumed']=True
        with self.assertRaisesRegex(ValueError,'hidden'):prepare(recipe,snapshot,0,2,include_effects=True)

    def test_exact_identity_scalar_precision_visibility_and_duplicates(self):
        recipe,snapshot=fixture();row=snapshot['rows'][0]
        snapshot['rows'].extend([copy.deepcopy(row),dict(row,subsumed=True)])
        local,state,ids,rows=prepare(recipe,snapshot,0,2)
        self.assertEqual(len(rows),1);self.assertEqual(state['present'].sum(),1)
        self.assertFalse(state['scalar_numeric'][0,0]);self.assertTrue(state['scalar_valid'][0,0])
        self.assertNotEqual(state['slots'][0,0],state['slots'][0,1])
        self.assertTrue(np.isfinite(state['tokens']).all())
        expected=reference_keys(recipe['rules'][0],rows,ids,state['keys'].shape[1])
        self.assertEqual(expected,{(0,ids[identity(row['values'][0])],ids[identity(row['values'][1])])})

    def test_missing_visibility_or_incorrect_sort_is_rejected(self):
        for mode in ('visibility','sort'):
            recipe,snapshot=fixture()
            if mode=='visibility':del snapshot['rows'][0]['subsumed']
            else:snapshot['rows'][0]['values'][1]['sort']='Other'
            with self.assertRaises(ValueError):prepare(recipe,snapshot,0,2)

    def test_reference_join_checks_repeated_variables(self):
        rule=dict(slots=[dict(definition='query')],query=[dict(call=dict(table='P'),args=[dict(slot=0),dict(slot=0)])])
        a=dict(sort='E',eq='Cell(1)');b=dict(sort='E',eq='Cell(2)')
        rows=[dict(table='P',values=[a,b]),dict(table='P',values=[b,b])];ids={identity(a):0,identity(b):1}
        self.assertEqual(reference_keys(rule,rows,ids,2),{(0,1)})

if __name__=='__main__':unittest.main()

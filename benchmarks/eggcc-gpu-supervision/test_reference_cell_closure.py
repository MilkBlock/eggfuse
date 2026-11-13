import unittest
from reference_cell_closure import saturate,facts_from_cells
from device_snapshot_import import identity,prepare_family
from test_device_snapshot_import import fixture


class ReferenceClosure(unittest.TestCase):
    def test_new_fact_is_consumed_only_in_next_run(self):
        def rule(table,dest,arg):return dict(query=[dict(call=dict(table=table),args=[dict(slot=0),dict(slot=1)])],effects=[dict(kind='construct',call=dict(table=dest),args=[dict(slot=arg)],dst=2)])
        a=dict(sort='E',eq='Cell(1)');b=dict(sort='E',eq='Cell(2)')
        rows=[dict(table='Seed',values=[a,b])];ids={identity(a):0,identity(b):1}
        facts,changes,applications=saturate([rule('Seed','F',0),rule('F','G',1)],rows,ids)
        self.assertEqual(changes,[1,1,0]);self.assertEqual(applications,[1,2,2])
        f=('construct','F',(('seed',0),))
        self.assertEqual(facts[('G',(f,))],('construct','G',(f,)))
        with self.assertRaisesRegex(ValueError,'budget'):saturate([rule('Seed','F',0)],rows,ids,max_runs=1)

    def test_family_import_keeps_all_original_rules_before_seed_templates(self):
        recipe,snapshot=fixture();recipe['rules'].append(recipe['rules'][0])
        local,state,ids,rows=prepare_family(recipe,snapshot,[0,1],3)
        self.assertEqual(len(local['rules']),3);self.assertEqual(int(state['keys'][0,0]),2)
        self.assertEqual(local['rules'][:2],recipe['rules'])
        facts,complete=facts_from_cells(local,state)
        self.assertTrue(complete);self.assertEqual(facts,[('F',(0,),1)])
        local['rules'][2]['effects']=[dict(kind='copy',arg=dict(slot=1),dst=0)]
        facts,complete=facts_from_cells(local,state)
        self.assertFalse(complete);self.assertEqual(facts,[])
        with self.assertRaises(ValueError):prepare_family(recipe,snapshot,[0,0],3)

if __name__=='__main__':unittest.main()

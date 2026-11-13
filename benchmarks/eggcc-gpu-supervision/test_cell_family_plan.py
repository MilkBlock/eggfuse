import unittest
from cell_family_plan import project_control,withhold,family
from reference_cell_closure import scheduled
from device_snapshot_import import identity

class FamilyTests(unittest.TestCase):
    def test_projection_preserves_order_and_nested_control(self):
        source=dict(sequence=[dict(run='omit'),dict(repeat=2,body=dict(sequence=[dict(saturate=dict(sequence=[dict(run='p'),dict(run='omit')])),dict(run='c')]))])
        projected=project_control(source,{'p','c'})
        self.assertEqual(projected,dict(sequence=[dict(repeat=2,body=dict(sequence=[dict(saturate=dict(sequence=[dict(run='p')])),dict(run='c')]))]))
        self.assertIsNone(project_control(source,{'missing'}))
        with self.assertRaises(ValueError):project_control(dict(unknown=1),{'p'})
        recipe=dict(control=[source],rules=[dict(metadata=dict(source_set='p')),dict(metadata=dict(source_set='c'))])
        self.assertEqual(family(recipe,dict(rules=[0,1],stages=['p','c'],control_path=[0]))[2],projected)
        with self.assertRaises(ValueError):family(recipe,dict(rules=[0],stages=['c'],control_path=[0]))

    def test_snapshot_selector_uses_typed_existing_relations(self):
        sort=dict(kind='eq',name='E');other=dict(kind='eq',name='F')
        recipe=dict(tables=[dict(name='Source',schema=[sort,sort]),dict(name='Target',schema=[sort,other])])
        val=lambda n:dict(sort='E',eq=str(n))
        rows=[dict(table='Source',subsumed=False,values=[val(1),val(2)]),dict(table='Target',subsumed=False,values=[val(1),dict(sort='F',eq='a')]),dict(table='Target',subsumed=False,values=[val(3),dict(sort='F',eq='b')])]
        config=dict(remove_rows=[dict(table='Target',column=0,from_table='Source',from_columns=[0])])
        out,n=withhold(dict(rows=rows),recipe,config)
        self.assertEqual(n,1);self.assertEqual(out['rows'],[rows[0],rows[2]])
        config['remove_rows'][0]['column']=1
        with self.assertRaises(ValueError):withhold(dict(rows=rows),recipe,config)

    def test_reference_stages_do_not_run_a_future_consumer_early(self):
        def rule(stage,src,dst):
            return dict(metadata=dict(source_set=stage),query=[dict(call=dict(table=src),args=[dict(slot=0),dict(slot=1)])],effects=[dict(kind='construct',call=dict(table=dst),args=[dict(slot=1)],dst=2)])
        rules=[rule('p','F','G'),rule('c','G','H')]
        values=[dict(sort='E',eq=str(i)) for i in (1,2)]
        rows=[dict(table='F',values=values)];ids={identity(v):i for i,v in enumerate(values)}
        stage=lambda name:dict(saturate=dict(run=name))
        facts,logs=scheduled(rules,rows,ids,dict(sequence=[stage('p'),stage('c')]))
        self.assertEqual([l['stage'] for l in logs],['p','p','c','c'])
        self.assertEqual([l['new_facts'] for l in logs],[1,0,1,0])
        self.assertEqual({k[0] for k in facts},{'F','G','H'})
        facts,logs=scheduled(rules,rows,ids,dict(sequence=[stage('c'),stage('p')]))
        self.assertNotIn('H',{k[0] for k in facts})
        with self.assertRaises(ValueError):scheduled(rules,rows,ids,dict(sequence=[stage('p'),stage('c')]),max_runs=2)

if __name__=='__main__':unittest.main()

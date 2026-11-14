import unittest
from unittest.mock import patch
from synthetic_native_source import control,emit
from audit_native_synthetic import compare

class NativeSourceTests(unittest.TestCase):
    def fixture(self):
        sort=dict(kind='eq',name='Expr')
        recipe=dict(tables=[dict(name='F',kind='constructor',schema=[sort,sort])],rules=[])
        snapshot=dict(rows=[dict(table='F',values=[dict(sort='Expr',eq='a'),dict(sort='Expr',eq='a')],subsumed=False)])
        return recipe,snapshot

    def test_control(self):
        self.assertEqual(control(dict(sequence=[dict(saturate=dict(run='a')),dict(run='b')])), '(seq (saturate (run a)) (run b))')
        with self.assertRaises(ValueError):control(dict(run='a)'))

    def test_no_global_alias_tables(self):
        with patch('synthetic_native_source.validate',return_value=self.fixture()):
            source=emit({},dict(sequence=[]))
        self.assertNotIn('(let seed',source)
        self.assertIn('(union (SyntheticSeed_Expr 0) (F (SyntheticSeed_Expr 0)))',source)

    def test_exact_graph_and_corruptions(self):
        recipe,snapshot=self.fixture()
        rows=snapshot['rows']+[dict(table='SyntheticSeed_Expr',subsumed=False,values=[dict(sort='i64',value=0),dict(sort='Expr',eq='a')])]
        trace=dict(final=dict(rows=rows),runs=[],strict_run_graphs_equal=True,strict_audit_reference_equal=True,run_control_counts_equal=True)
        with patch('audit_native_synthetic.validate',return_value=(recipe,snapshot)):
            self.assertTrue(compare({},trace,dict(sequence=[]))['passed'])
            trace['final']['rows']=rows[1:]
            self.assertFalse(compare({},trace,dict(sequence=[]))['passed'])
            trace['final']['rows']=rows
            trace['strict_run_graphs_equal']=False
            self.assertFalse(compare({},trace,dict(sequence=[]))['passed'])
            rows[-1]['values'][0]['value']=7
            with self.assertRaises(ValueError):compare({},trace,dict(sequence=[]))

if __name__=='__main__':unittest.main()

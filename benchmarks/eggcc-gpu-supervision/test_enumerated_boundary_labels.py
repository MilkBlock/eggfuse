import copy,unittest
from unittest.mock import patch
from enumerated_boundary_labels import label

class BoundaryLabels(unittest.TestCase):
    def test_final_anchor_equivalence_and_missing_evidence(self):
        ports=[dict(sort='E',eq='a'),dict(sort='E',eq='b')]
        snap=dict(rows=[dict(values=ports)])
        rows=[dict(table='SyntheticSeed_E',subsumed=False,values=[dict(sort='i64',value=i),dict(sort='E',eq='final')]) for i in range(2)]
        trace=dict(strict_run_graphs_equal=True,strict_audit_reference_equal=True,run_control_counts_equal=True,final=dict(rows=rows))
        with patch('enumerated_boundary_labels.validate',return_value=({},snap)):
            result=label(dict(input_sha256='test'),trace)
            self.assertEqual(result['partition'],[0,0]);self.assertEqual(result['new_boundary_equalities'],1)
            bad=copy.deepcopy(trace);bad['final']['rows'].pop()
            with self.assertRaises(ValueError):label(dict(input_sha256='test'),bad)
            bad=copy.deepcopy(trace);bad['final']['rows'][1]['values'][0]['value']=0
            with self.assertRaises(ValueError):label(dict(input_sha256='test'),bad)

if __name__=='__main__':unittest.main()

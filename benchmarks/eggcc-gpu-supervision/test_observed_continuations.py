import copy,unittest
from collect_observed_continuations import collect
from test_cell_token_successors import rule,atom,make,TABLES
from test_observed_cell_targets import binding


def fixture():
    producer=rule([atom('F',0,1),atom('G',2,3)],[dict(kind='union',args=[dict(slot=0),dict(slot=2)])],4)
    consumer=rule([atom('F',0,1),atom('G',0,2)],[make('Pair',3,1,2)],3)
    a=binding([10,11,20,21],[10,11,10,21]);a['rule']=0
    b=binding([10,11,21]);b['rule']=1
    program=dict(sha256='x',recipe=dict(rules=[producer,consumer],tables=list(TABLES.values())))
    trace=dict(program_sha256='x',strict_audit_reference_equal=True,run_control_counts_equal=True,steps=[dict(ordinal=1,ruleset='producer',executed_bindings=1),dict(ordinal=2,ruleset='empty',executed_bindings=0),dict(ordinal=3,ruleset='consumer',executed_bindings=1)],runs=[dict(ordinal=1,audit=dict(bindings=[a])),dict(ordinal=3,audit=dict(bindings=[b]))])
    return program,trace


class ObservedContinuation(unittest.TestCase):
    def test_actual_changed_request_and_empty_run_boundary(self):
        p,t=fixture();rows,counts=collect(p,t,'case','test')
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['empty_intervening_runs'],[2]);self.assertTrue(rows[0]['source_run_validated']);self.assertTrue(rows[0]['second_completion']['novel'])
        self.assertEqual(counts['proven_observed_occurrences'],1)

    def test_external_native_union_is_not_local_proof(self):
        p,t=fixture();t['runs'][0]['audit']['bindings'][0]['eq_ports'][3]['after']=11
        rows,counts=collect(p,t,'case','test');self.assertFalse(rows);self.assertEqual(counts['outside_local_equality'],1)

    def test_all_consumer_premises_required(self):
        p,t=fixture();p['recipe']['rules'][1]['query'].append(atom('Pair',0,1,2))
        rows,counts=collect(p,t,'case','test');self.assertFalse(rows);self.assertEqual(counts['local_premise:missing consumer premise'],1)

    def test_gap_with_effects_or_missing_audit_rejected(self):
        p,t=fixture();t['steps'][1]['executed_bindings']=1
        self.assertFalse(collect(p,t,'case','test')[0])
        t['strict_audit_reference_equal']=False
        with self.assertRaises(ValueError):collect(p,t,'case','test')

if __name__=='__main__':unittest.main()

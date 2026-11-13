import copy
import unittest
from hash_memory import compare


def snapshot():
    return dict(program_sha256='p',runs=2,final_state_sha256='s',
        source_storage={'fact_lifecycle':{'frames':[]},'completed_owners':{'stored_fact_entries':3}},
        ownership_storage={'components':[], 'shapes':[]},
        graph_fields=[['cells',100]], graph_owned_teardown_bytes=100, max_takeover_extra_bytes=10,
        execution_and_takeover_peak_bytes=1000, retained_program_teardown_bytes=800)


class MemoryComparisonTests(unittest.TestCase):
    def test_counts_actual_hash_arrays(self):
        a=snapshot();b=copy.deepcopy(a)
        b['source_storage']['completed_owners']['stored_hash_bytes']=8
        b['graph_owned_teardown_bytes']=84
        result=compare(a,b)
        self.assertEqual(result['hash_saved'],16)
        self.assertEqual(result['graph_saved'],16)

    def test_state_and_lifecycle_changes_are_rejected(self):
        a=snapshot();b=copy.deepcopy(a)
        b['final_state_sha256']='different'
        with self.assertRaises(ValueError):compare(a,b)
        b=copy.deepcopy(a)
        b['source_storage']['fact_lifecycle']['frames']=[{'cell':1}]
        with self.assertRaises(ValueError):compare(a,b)

    def test_wiring_change_is_not_accepted_as_compression(self):
        a=snapshot();b=copy.deepcopy(a)
        b['ownership_storage']['components']=[{'id':1}]
        with self.assertRaises(ValueError):compare(a,b)

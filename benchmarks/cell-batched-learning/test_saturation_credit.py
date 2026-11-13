import copy
import unittest
from saturation_credit import covered_work


class CreditTests(unittest.TestCase):
    def setUp(self):
        self.program = {'known_results': {'static_aliases': [{'rule': 0, 'operation': 1}]},
                        'recipe': {'rules': [{'metadata': {'source_set': 'stage'},
                                             'effects': [{'op': 'copy'}, {'op': 'let', 'kind': 'construct'},
                                                         {'op': 'let', 'kind': 'construct'}, {'op': 'union'}]}]}}
        self.row = {'rule': 0, 'outcome': 'rhs_covered', 'counts': {
            'applications': 3, 'rhs_ops': 12, 'prefix_copy_ops': 3,
            'prefix_static_alias_ops': 3, 'prefix_remaining_effect_ops': 6}}

    def test_no_double_credit_for_alias_or_copy(self):
        work = covered_work(self.program, [self.row])[0]['work']
        self.assertEqual(work, {'copies': 3, 'static_aliases': 3,
                                'remaining_construct': 3, 'remaining_union': 3})

    def test_partial_prefix_does_not_establish_full_coverage(self):
        row = dict(self.row, outcome='missing_local_constructor')
        self.assertEqual(covered_work(self.program, [row]), [])

    def test_local_rule_number_does_not_determine_identity(self):
        first = covered_work(self.program, [self.row])[0]['rule_key']
        other = copy.deepcopy(self.program)
        other['recipe']['rules'].insert(0, {'effects': []})
        other['known_results']['static_aliases'][0]['rule'] = 1
        row = dict(self.row, rule=1)
        self.assertEqual(first, covered_work(other, [row])[0]['rule_key'])

    def test_mismatched_operation_count_rejected(self):
        row = copy.deepcopy(self.row)
        row['counts']['rhs_ops'] += 1
        with self.assertRaises(AssertionError):
            covered_work(self.program, [row])

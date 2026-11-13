import copy
import unittest
from witness_plans import prove


class WitnessProofTests(unittest.TestCase):
    def setUp(self):
        self.program = {'recipe': {'tables': [{'name': 'F'}, {'name': 'G'}], 'rules': [{
            'query': [{'call': {'table': 'F'}, 'args': [{'slot': 0}, {'slot': 1}]}],
            'effects': [{'op': 'let', 'dst': 2, 'call': {'table': 'G'}, 'args': [{'slot': 0}]}]}]}}
        self.storage = {'shapes': [{'programs': [0, 0], 'ports': [[0, 1], [0, 2]]}],
                        'programs': [{'fields': [[0, 1]]}], 'operators': [[0], [1]]}
        self.recipe = {'rule': 0, 'shape': 0, 'frame_codes': [0, 1],
                       'query_sites': [[0, 0, 0]], 'rhs_sites': [[0, 1, 0]]}

    def test_same_port_layout_different_operators(self):
        self.assertEqual(prove(self.program, self.storage, self.recipe), [])
        wrong = copy.deepcopy(self.recipe)
        wrong['frame_codes'][1] = 0
        with self.assertRaises(ValueError):
            prove(self.program, self.storage, wrong)

    def test_unproved_equality_remains_an_obligation(self):
        self.storage['shapes'][0]['ports'][1][0] = 3
        self.assertEqual(prove(self.program, self.storage, self.recipe), ['dynamic_key_equality'])

    def test_scalar_is_not_proved_by_observed_values(self):
        self.storage['programs'][0]['fields'][0][0] = None
        self.assertEqual(prove(self.program, self.storage, self.recipe), ['scalar_key_check'])

    def test_absent_query_anchor_does_not_bind_inputs(self):
        self.recipe['query_sites'] = []
        self.assertEqual(prove(self.program, self.storage, self.recipe), ['external_eq_key_check'])

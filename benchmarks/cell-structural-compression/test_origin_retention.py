import unittest
from analyze_origin_retention import readers


class ReadObligations(unittest.TestCase):
    def test_effect_writes_are_not_reads_but_rhs_and_merge_reads_are(self):
        program = {'recipe': {'rules': [{'query': [{'call': {'table': 'Q'}}],
                    'effects': [{'op': 'set', 'call': {'table': 'Receipt'}},
                                {'op': 'let', 'call': {'table': 'R'}}]}],
                    'control': []},
                   'merge_programs': {'programs': [{'table': 'Destination',
                       'operations': [{'call': {'table': 'Mutable'}}]}]}}
        found = readers(program)
        self.assertEqual(found['Q'], [['query', 0]])
        self.assertEqual(found['R'], [['rhs_read', 0, 1]])
        self.assertEqual(found['Mutable'], [['merge_read', 'Destination']])
        self.assertNotIn('Receipt', found)
        self.assertNotIn('Destination', found)


if __name__ == '__main__':
    unittest.main()

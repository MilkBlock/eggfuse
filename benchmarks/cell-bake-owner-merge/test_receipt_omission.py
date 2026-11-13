import copy
import unittest
from receipt_omission import project


class ReceiptProjection(unittest.TestCase):
    def setUp(self):
        self.core = dict(tables=[dict(name='receipt', kind='function', merge='old',
                                     schema=[dict(name='Unit', kind='Unit')])],
                         rulesets=[dict(rules=[dict(body=[], head=[dict(
                             op='set', call=dict(table='receipt'), args=[],
                             value=dict(literal=0, sort=dict(name='Unit', kind='Unit')))])])],
                         initial=[], schedule=[])

    def test_only_membership_write_removed(self):
        before = copy.deepcopy(self.core)
        projected, count = project(self.core, {'receipt'})
        self.assertEqual(count, 1)
        self.assertEqual(projected['tables'], [])
        self.assertEqual(projected['rulesets'][0]['rules'][0]['head'], [])
        self.assertEqual(before, self.core)

    def test_readers_in_all_contexts_rejected(self):
        for key in ('initial', 'schedule', 'assertion_tables'):
            with self.subTest(key=key):
                core = copy.deepcopy(self.core)
                core[key] = [dict(call=dict(table='receipt'))]
                with self.assertRaisesRegex(ValueError, 'remaining receipt reference'):
                    project(core, {'receipt'})
        self.core['rulesets'][0]['rules'][0]['body'] = [dict(call=dict(table='receipt'))]
        with self.assertRaisesRegex(ValueError, 'remaining receipt reference'):
            project(self.core, {'receipt'})

    def test_computation_or_nonunit_write_rejected(self):
        effect = self.core['rulesets'][0]['rules'][0]['head'][0]
        effect['args'] = [dict(call=dict(table='F'), args=[])]
        with self.assertRaisesRegex(ValueError, 'evaluates an expression'):
            project(self.core, {'receipt'})
        effect['args'] = []
        effect['value']['literal'] = 1
        with self.assertRaisesRegex(ValueError, 'non-membership effect'):
            project(self.core, {'receipt'})


if __name__ == '__main__':
    unittest.main()

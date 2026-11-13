import unittest
from source_query_audit import align


def step(name, count=0, changed=False):
    return dict(ruleset=name, logical_matches=count, executed_bindings=count, changed=changed)


class SourceAlignment(unittest.TestCase):
    def test_maintenance_and_idle_source_only(self):
        a=[step('a', 3, True),step('cell-spine-complete', 2, True),step('a'),step('b', 1)]
        b=[step('a', 3, True),step('b', 1)]
        result=align(a,b)
        self.assertEqual(result['matched_source_runs'],2)
        self.assertEqual(result['removed_maintenance_runs'],1)
        self.assertEqual(len(result['removed_idle_source_runs']),1)

    def test_live_run_cannot_disappear(self):
        for removed in [step('x',1),step('x',changed=True)]:
            with self.assertRaises(ValueError):
                align([step('a'),removed,step('b')],[step('a'),step('b')])

    def test_work_change_and_new_run_rejected(self):
        with self.assertRaises(ValueError): align([step('a',2)],[step('a',1)])
        with self.assertRaises(ValueError): align([step('a')],[step('a'),step('b')])


if __name__ == '__main__': unittest.main()

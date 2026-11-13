import unittest

from full_program import lower, replay


class ControlContract(unittest.TestCase):
    def check(self, control, executions):
        code, registers = lower(control, {'a': [], 'b': []})
        return replay(code, registers,
                      [dict(ruleset=name, changed=changed) for name, changed in executions])

    def test_whole_sequence_controls_saturation(self):
        self.check([{'saturate': {'sequence': [{'run': 'a'}, {'run': 'b'}]}}],
                   [('a', True), ('b', False), ('a', False), ('b', False)])

    def test_nested_saturation_retains_outer_change(self):
        self.check([{'saturate': {'sequence': [
            {'saturate': {'run': 'a'}}, {'run': 'b'}]}}],
            [('a', True), ('a', False), ('b', False), ('a', False), ('b', False)])

    def test_repeat_stops_when_unchanged(self):
        self.check([{'repeat': 5, 'body': {'run': 'a'}}], [('a', False)])

    def test_repeat_bounds_changing_body(self):
        self.check([{'repeat': 2, 'body': {'run': 'a'}}], [('a', True), ('a', True)])

    def test_zero_repeat_and_empty_saturation(self):
        self.check([{'repeat': 0, 'body': {'run': 'a'}},
                    {'saturate': {'sequence': []}}], [])

    def test_rejects_missing_and_extra_runs(self):
        with self.assertRaises(ValueError):
            self.check([{'run': 'a'}], [])
        with self.assertRaises(ValueError):
            self.check([{'run': 'a'}], [('a', False), ('b', False)])

    def test_unknown_control_is_not_silently_dropped(self):
        with self.assertRaises(ValueError):
            lower([{'run': 'a', 'until': []}], {'a': []})


if __name__ == '__main__':
    unittest.main()

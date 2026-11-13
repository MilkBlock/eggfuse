import unittest
import test_settled_history as fixtures
from analyze_settled_capture import summarize


class SettledCaptureTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.SettledHistoryTests()
        fixture.setUp()
        self.trace, self.catalog = fixture.trace, fixture.catalog
        self.trace['runs'] = 2
        self.event = self.trace['completed_history']['events'][1]
        self.event['unit'] = 1
        self.program = {'sha256': 'p', 'iterative_bake': {'rhs_handoffs': {
            'states': [{'unit': 1}], 'completion_states': [{'back': 1}]}}}

    def test_missing_observation_is_not_zero_work(self):
        group = summarize(self.trace, self.catalog, self.program)['groups'][0]
        self.assertTrue(group['installed_direct_plan'])
        self.assertEqual(group['missing_capture_observation'], 1)
        self.assertNotIn('zero_allocation_captures', group)

    def test_existing_plan_does_not_erase_measured_allocations(self):
        self.event['capture'] = dict(allocations=2, slots=3, reads=4,
            inherited=1, shared_slots=0, empty_slots=0, heap_frames=1)
        group = summarize(self.trace, self.catalog, self.program)['groups'][0]
        self.assertEqual(group['allocations'], 2)
        self.assertEqual(group['zero_allocation_captures'], 0)
        self.assertEqual(group['slots'], 3)


if __name__ == '__main__':
    unittest.main()

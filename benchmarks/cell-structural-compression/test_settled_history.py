import copy
import unittest
from analyze_settled_history import analyze


class SettledHistoryTests(unittest.TestCase):
    def setUp(self):
        paths = [[[None, [1, None]]], [[None, [1, None]], [0, [2, 0]]]]
        implementations = [{'unit': i, 'class': i, 'source_path': path} for i, path in enumerate(paths)]
        self.catalog = {'program_sha256': 'p', 'implementations': [
            dict(u, ordered_class=u['class'], settled_class=0, ports=[], ordered_normalization='flat')
            for u in implementations]}
        self.trace = {'all_saved_run_checks_equal': True, 'completed_history': {
            'program_sha256': 'p', 'dropped_events': 0, 'event_units': [0, 1],
            'contracts': {'implementations': implementations},
            'events': [{'parent': None, 'run': 1, 'entry': [1, None], 'truncated_parent': False},
                       {'parent': 0, 'run': 2, 'entry': [2, 0], 'truncated_parent': False}],
            'closure_transfers': {'transfers': [{'unit': 1, 'after_source_runs': {
                'kind': 'saturated', 'prefix_stages': 1, 'required_entry_facts': [],
                'prefix_ports_injective': True, 'strengthened_prefix_ports': [],
                'introduced_facts': [], 'ordered_union_obligations': 0}}]}}}

    def test_equal_settled_state_is_not_equal_ordered_path(self):
        r = analyze(self.trace, self.catalog)
        self.assertEqual(r['counts']['same_ordered_class'], 0)
        self.assertEqual(r['counts']['same_state_exact_prefix'], 1)
        self.assertEqual(r['depth_if_equal_settled_edges_folded'], {1: 2})

    def test_opaque_states_do_not_merge(self):
        for u in self.catalog['implementations']:
            u['settled_class'] = None
        self.assertEqual(analyze(self.trace, self.catalog)['counts']['same_settled_class'], 0)

    def test_unsettled_run_is_rejected(self):
        self.trace['completed_history']['events'][1]['run'] = 1
        with self.assertRaisesRegex(ValueError, 'unsettled'):
            analyze(self.trace, self.catalog)

    def test_guarded_certificate_cannot_claim_saturation(self):
        self.trace['completed_history']['closure_transfers']['transfers'][0]['after_source_runs']['required_entry_facts'] = [1]
        with self.assertRaisesRegex(ValueError, 'inconsistent'):
            analyze(self.trace, self.catalog)

    def test_mismatched_source_and_truncated_archive_are_rejected(self):
        wrong = copy.deepcopy(self.catalog)
        wrong['implementations'][1]['source_path'] = []
        with self.assertRaisesRegex(ValueError, 'source path'):
            analyze(self.trace, wrong)
        self.trace['completed_history']['dropped_events'] = 1
        with self.assertRaisesRegex(ValueError, 'complete audited'):
            analyze(self.trace, self.catalog)


if __name__ == '__main__':
    unittest.main()

import copy
import unittest
from analyze_handoff_trace import analyze


class HandoffTrace(unittest.TestCase):
    def fixture(self):
        p = {'sha256': 'p', 'recipe': {'rules': [
            {'query': [], 'effects': []}, {'effects': [], 'query': [{'call': {'table': 'View'}, 'args': [{'slot': 0}]}]}]}}
        t = {'all_saved_run_checks_equal': True, 'runs': 3,
             'completed_history': {'program_sha256': 'p', 'dropped_events': 0,
                 'events': [{'execution': {'cell': 4}, 'run': 1, 'entry': [0, None], 'parent': None}]},
             'handoff': {'table': 'View', 'windows': [{'run': 3,
                 'before': [{'values': [{'Eq': 7}], 'origin': {'cell': 4, 'op': 0}, 'hidden': False}],
                 'observation': {'effective_writes': [], 'matches': [{'rule': 1, 'ordinal': 2,
                    'values': {'0': {'Eq': 7}}, 'continuation': None, 'direct': False}]}}]}}
        return p,t

    def test_root_match_recovers_prior_run_source_without_inventing_cursor(self):
        p,t = self.fixture()
        r = analyze(p,t)
        self.assertEqual(r['totals']['exact_cross_run_links'], 1)
        self.assertEqual(r['groups'][0]['without_query_continuation'], 1)
        self.assertEqual(r['groups'][0]['min_run_gap'], 2)

    def test_missing_or_different_binding_is_not_an_equality_proof(self):
        p,t = self.fixture()
        for values in ({}, {'0': {'Eq': 8}}):
            changed = copy.deepcopy(t)
            changed['handoff']['windows'][0]['observation']['matches'][0]['values'] = values
            r = analyze(p,changed)
            self.assertEqual(r['links'], [])

    def test_dropped_or_future_source_rejected(self):
        p,t = self.fixture()
        t['completed_history']['dropped_events'] = 1
        with self.assertRaises(ValueError):
            analyze(p,t)
        t['completed_history']['dropped_events'] = 0
        t['completed_history']['events'][0]['run'] = 3
        with self.assertRaises(ValueError):
            analyze(p,t)


if __name__ == '__main__':
    unittest.main()

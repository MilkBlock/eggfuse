import copy
import unittest
from audit_history_refresh import observations, analyze
from test_rhs_links import fixture


class HistoryRefresh(unittest.TestCase):
    def test_first_run_alternatives_preserved_and_roots_separated(self):
        trace = fixture()
        original = trace['runs'][0]['audit']['bindings'][1]
        trace['runs'][0]['audit']['bindings'].append(copy.deepcopy(original))
        later = copy.deepcopy(original)
        later['rhs']['slots'][0]['eq_port']['after_run'] = 99
        trace['runs'][1]['audit']['bindings'].append(later)
        replacements, counts = observations(trace)
        self.assertEqual(replacements[(3, 2, 0)]['identity'], [(1, 1, 0), (1, 2, 0)])
        self.assertEqual(replacements[(3, 2, 0)]['identity_root'], [(3, 2, 0)])
        self.assertEqual(counts['reobserved_identity'], 1)
        self.assertNotIn('reobserved_identity_and_root', counts)

    def test_incomplete_state_not_retained(self):
        trace = fixture(); trace['runs'][0]['audit']['bindings'][1]['rhs']['completed'] = False
        replacements, _ = observations(trace)
        self.assertNotIn((1, 1, 0), replacements)

    def test_historical_alternatives_deduplicated_per_input_port(self):
        trace = fixture()
        original = copy.deepcopy(trace['runs'][0]['audit']['bindings'][1])
        original['eq_ports'] = []
        trace['runs'][0]['audit']['bindings'] = [copy.deepcopy(original), copy.deepcopy(original)]
        trace['runs'][1]['audit']['bindings'] = [copy.deepcopy(original), copy.deepcopy(original)]
        for ordinal in (4, 5):
            trace['runs'].append(dict(ordinal=ordinal, audit=dict(bindings=[dict(
                rule=1, values=[], eq_ports=[dict(slot=0, sort='E', identity=20, before=10)],
                rhs=dict(completed=True, slots=[]))])))
            trace['steps'].append(dict(ordinal=ordinal, ruleset='c', executed_bindings=1, changed=True))
        result = analyze(trace)['counterfactuals']
        # Last consumer has two historical alternatives. Redirecting both to the
        # same two earliest alternatives must not multiply them into four.
        self.assertEqual(result['latest']['edges'], 4)
        self.assertEqual(result['identity']['edges'], 4)

    def test_adjacent_graph_unchanged(self):
        result = analyze(fixture())
        for mode in ('identity', 'identity_root'):
            self.assertEqual(result['counterfactuals'][mode]['layers'], result['counterfactuals']['latest']['layers'])
            self.assertEqual(result['counterfactuals'][mode]['edges'], result['counterfactuals']['latest']['edges'])
        self.assertFalse(result['takeover_authorized'])


if __name__ == '__main__':
    unittest.main()

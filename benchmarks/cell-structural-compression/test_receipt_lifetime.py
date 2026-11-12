import copy
import unittest
from analyze_receipt_lifetime import analyze


def fixture():
    old, new = {'Fact': {'cell': 1, 'op': 0}}, {'Fact': {'cell': 2, 'op': 0}}
    events = [
        {'run': 1, 'event': {'kind': 'capture', 'rule': 3, 'slot': 0, 'witness': old}},
        {'run': 2, 'event': {'kind': 'forward', 'from': old, 'to': new, 'epoch': 2}},
        {'run': 2, 'event': {'kind': 'clear', 'edges': 1, 'epoch': 2}},
        {'run': 3, 'event': {'kind': 'failure', 'rule': 4, 'site': {'Effect': 1}, 'slot': 1,
                            'table': 10, 'original': old, 'resolved': old, 'archived_target': new,
                            'hops': 1, 'target_table': 10, 'target_visible': True}},
        {'run': 4, 'event': {'kind': 'capture', 'rule': 3, 'slot': 0, 'witness': old}},
    ]
    return {'program_sha256': 'test', 'runs': 4, 'all_saved_run_checks_equal': True,
            'stage_work': {'ripsat_witness_fallbacks': 1, 'ripsat_witness_missing': 0},
            'receipt_trace': {'schema': 'cell-receipt-lifetime-trace/v1', 'complete_archive': True,
                              'trace': {'dropped': 0, 'events': events}}}


class ReceiptLifetimeTests(unittest.TestCase):
    def test_uses_only_evidence_before_failure(self):
        result = analyze(fixture())
        self.assertEqual(result['historical_target_visible_at_failure'], 1)
        self.assertEqual(result['historical_chain_crosses_clear'], 1)
        self.assertEqual(result['historical_chain_crosses_source_run'], 1)
        self.assertEqual(len(result['details'][0]['captures_of_original']), 1)

    def test_refuses_partial_or_inconsistent_archive(self):
        for mutation in ['dropped', 'target', 'clear', 'counter']:
            run = fixture()
            if mutation == 'dropped':
                run['receipt_trace']['trace']['dropped'] = 1
            elif mutation == 'target':
                run['receipt_trace']['trace']['events'][3]['event']['archived_target'] = {'Function': 9}
            elif mutation == 'clear':
                run['receipt_trace']['trace']['events'][2]['event']['edges'] = 2
            else:
                run['stage_work']['ripsat_witness_fallbacks'] = 2
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                analyze(run)

    def test_parent_candidates_require_current_not_archived_proof(self):
        run = fixture()
        events = run['receipt_trace']['trace']['events']
        edge = events[1]['event']
        candidate = {'run': 2, 'event': {'kind': 'parent_forward', 'child': 3,
            'from': edge['from'], 'to': edge['to'], 'source_users': 1,
            'source_facts': 0, 'source_slots': 5, 'target_visible': True, 'parent_cycle': True}}
        events.insert(2, candidate)
        result = analyze(run)['parent_forwarding']
        self.assertEqual(result['single_holder_factless_sources'], 1)
        self.assertEqual(result['parent_cycles'], 1)
        events[2], events[3] = events[3], events[2]
        with self.assertRaisesRegex(ValueError, 'current forwarding'):
            analyze(run)

    def test_refuses_forwarding_cycles(self):
        run = fixture()
        edge = copy.deepcopy(run['receipt_trace']['trace']['events'][1])
        edge['event']['from'], edge['event']['to'] = edge['event']['to'], edge['event']['from']
        run['receipt_trace']['trace']['events'].insert(2, edge)
        run['receipt_trace']['trace']['events'][3]['event']['edges'] = 2
        with self.assertRaisesRegex(ValueError, 'cyclic'):
            analyze(run)


if __name__ == '__main__':
    unittest.main()

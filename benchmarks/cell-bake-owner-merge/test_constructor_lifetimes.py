import unittest
from constructor_lifetimes import analyze, missing_membership


def address(cell, op=0):
    return dict(cell=cell, op=op)


def constructor(run, site, target, created):
    return dict(run=run, event=dict(kind='constructor', site=address(site),
                witness={'Fact': address(target)}, created=created, visible=True))


def retire(run, cell):
    return dict(run=run, event=dict(kind='retire', fact={'Fact': address(cell)}))


def archive(events):
    return dict(schema='cell-receipt-lifetime-trace/v1', complete_archive=True,
                constructor_coverage='generic only', trace=dict(dropped=0, events=events))


class LifetimeTests(unittest.TestCase):
    def test_foreign_reuse_and_retirement_across_runs(self):
        result = analyze(archive([constructor(1, 10, 10, True),
                                  constructor(2, 20, 10, False), retire(3, 10)]))['counts']
        self.assertEqual(result['foreign_source_reuses'], 1)
        self.assertEqual(result['reuse_of_observed_prior_run_birth'], 1)
        self.assertEqual(result['observed_births_later_retired'], 1)
        self.assertEqual(result['retired_across_runs'], 1)
        self.assertEqual(result['observed_births_without_later_retirement_event'], 0)

    def test_missing_birth_is_unknown_and_rebirth_starts_a_new_lifetime(self):
        result = analyze(archive([constructor(1, 20, 10, False), retire(2, 10),
                                  constructor(3, 10, 10, True)]))['counts']
        self.assertEqual(result['reused_target_birth_unobserved'], 1)
        self.assertEqual(result['retirements_without_observed_birth'], 1)
        self.assertEqual(result['observed_births_without_later_retirement_event'], 1)

    def test_missing_membership_requires_a_concrete_outcome(self):
        events = [constructor(1, 1, 1, True), constructor(1, 2, 99, False), retire(2, 1)]
        report = dict(receipt_trace=archive(events),
                      ownership_storage=dict(components=[dict(shape=0, frames=[1, 2, 3])],
                          shapes=[dict(programs=[0, 0, 0])], programs=[dict(fields=[[0]])]),
                      source_storage=dict(fact_lifecycle=dict(frames=[
                          dict(cell=c, facts=[], completed_storage=True) for c in (1, 2, 3)])))
        counts = missing_membership(report)
        self.assertEqual(counts['absent_owned_positions'], 3)
        self.assertEqual(counts['created_locally_then_retired'], 1)
        self.assertEqual(counts['last_result_was_another_fact_or_function'], 1)
        self.assertEqual(counts['no_constructor_outcome_observed'], 1)

    def test_reject_loss_old_observers_and_invalid_births(self):
        cases = [archive([]), archive([]), archive([constructor(1, 1, 2, True)])]
        cases[0]['complete_archive'] = False
        del cases[1]['constructor_coverage']
        for value in cases:
            with self.assertRaises(ValueError):
                analyze(value)


if __name__ == '__main__':
    unittest.main()

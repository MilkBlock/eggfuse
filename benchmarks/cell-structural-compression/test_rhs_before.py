import unittest
from analyze_rhs_before import analyze


def fixture(status='visible'):
    e = dict(run=2, rule=0, cell=7, operation=0, previous_rule=0, previous_run=1, prior_status=status,
             facts=0, receipt={'Fact': {'cell': 1, 'op': 0}}, success=True, forwarded=False)
    return dict(runs=2, all_saved_run_checks_equal=True, rhs_projection_trace=dict(
        complete_archive=True, trace=dict(dropped=0, boundary_dropped=0, boundaries=[e])))


class BeforeTests(unittest.TestCase):
    def test_visible_cross_run_is_separate_from_retired(self):
        self.assertEqual(analyze(fixture())['counts']['cross_run:visible'], 1)
        counts = analyze(fixture('retired'))['counts']
        self.assertNotIn('cross_run:visible', counts)
        self.assertEqual(counts['cross_run:retired'], 1)

    def test_failed_and_mutating_attempts_are_not_silenced(self):
        f = fixture()
        e = f['rhs_projection_trace']['trace']['boundaries'][0]
        e.update(facts=1, success=False)
        counts = analyze(f)['counts']
        self.assertEqual(counts['visible_prior_new_facts'], 1)
        self.assertEqual(counts['visible_prior_failed'], 1)

    def test_complete_cell_requires_every_unique_constructor_boundary(self):
        f = fixture()
        t = f['rhs_projection_trace']['trace']
        t['plans'] = [dict(constructor_sites=1)]
        t['events'] = [dict(cell=7, rule=0, constructor_requests=1, facts=0, updates=0, union_requests=0)]
        self.assertEqual(analyze(f)['all_constructor_boundaries_previously_visible']['cross_run_constructor_requests'], 1)
        t['plans'][0]['constructor_sites'] = 2
        t['boundaries'].append(dict(t['boundaries'][0]))
        self.assertEqual(analyze(f)['all_constructor_boundaries_previously_visible'], {})

    def test_invalid_archive_rejected(self):
        for kind in ('drop', 'future', 'unknown'):
            f = fixture()
            t = f['rhs_projection_trace']['trace']
            if kind == 'drop': t['boundary_dropped'] = 1
            elif kind == 'future': t['boundaries'][0]['previous_run'] = 3
            else: t['boundaries'][0]['prior_status'] = 'unknown'
            with self.assertRaises(ValueError): analyze(f)


if __name__ == '__main__': unittest.main()

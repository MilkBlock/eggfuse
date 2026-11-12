import unittest
from analyze_rhs_owners import analyze


def fixture():
    location = dict(component=7, shape=2, ordinal=0)
    receipt = {'Fact': dict(cell=3, op=1)}
    b = dict(cell=4, rule=0, operation=0, run=2, previous_run=1, previous_rule=0,
             prior_status='visible', forwarded=False, facts=0, success=True,
             prior_receipt=receipt, receipt=receipt,
             owner_links=dict(receiver=None, donor=location, parent=None, entry_present=True,
                 anchors=[dict(atom=0, location=location)], query=[], query_atoms=2))
    return dict(program_sha256='p', runs=2, all_saved_run_checks_equal=True,
                rhs_projection_trace=dict(complete_archive=True, trace=dict(
                    dropped=0, boundary_dropped=0, boundaries=[b], events=[])))


class OwnersTests(unittest.TestCase):
    def test_anchor_locates_donor_without_receiver_frame(self):
        r = analyze(fixture())
        self.assertEqual(r['counts']['cross_run:same_component_source'], 1)
        self.assertEqual(r['patterns'][0]['source_kind'], 'entry')

    def test_same_shape_in_other_component_is_not_reachable(self):
        a = fixture()
        a['rhs_projection_trace']['trace']['boundaries'][0]['owner_links']['donor'] = dict(component=8, shape=2, ordinal=0)
        self.assertEqual(analyze(a)['counts']['cross_run:no_observed_same_component_source'], 1)

    def test_complete_cell_requires_all_constructor_sites(self):
        a = fixture()
        t = a['rhs_projection_trace']['trace']
        t['events'] = [dict(cell=4, rule=0, constructor_requests=1)]
        t['plans'] = [dict(constructor_sites=1)]
        self.assertEqual(analyze(a)['complete_cells']['cross_run_constructor_requests'], 1)
        t['plans'][0]['constructor_sites'] = 2
        self.assertEqual(analyze(a)['complete_cells'], {})

    def test_missing_old_receipt_not_replaced_by_returned_receipt(self):
        a = fixture()
        a['rhs_projection_trace']['trace']['boundaries'][0]['prior_receipt'] = None
        with self.assertRaises(ValueError): analyze(a)


if __name__ == '__main__': unittest.main()

import unittest
from analyze_owner_gaps import entry_sources, analyze
from test_rhs_owners import fixture


class GapTests(unittest.TestCase):
    def test_entry_coordinate_is_not_query_atom(self):
        row = dict(atom=0, receipt={}, location=None)
        self.assertEqual(entry_sources(dict(anchors=[row], query=[]), [3]), {0: row})
        row = dict(entry=0, atom=3, receipt={}, location=None)
        self.assertEqual(entry_sources(dict(anchors=[row], query=[]), [3]), {0: row})
        row['atom'] = 0
        with self.assertRaises(ValueError): entry_sources(dict(anchors=[row], query=[]), [3])

    def test_capacity_uses_source_and_installed_transition_is_not_donor(self):
        a = fixture()
        b = a['rhs_projection_trace']['trace']['boundaries'][0]
        b['owner_links']['donor'] = dict(component=8, shape=9, ordinal=0, frames=1)
        source = b['owner_links']['anchors'][0]
        source['location']['frames'] = 2
        source['receipt'] = {'Fact': dict(cell=3, op=4)}
        c = dict(program_sha256='p', entries=[[3]], max_frames=4, transitions=[])
        self.assertEqual(analyze(c,a)['counts']['unbaked_transition_with_capacity'],1)
        c['transitions'] = [[dict(shape=2, hop=dict(source_frame=0, rule=0, entry=0, op=4)), 5]]
        self.assertEqual(analyze(c,a)['counts']['installed_transition_with_capacity'],1)
        source['location']['frames'] = 4
        self.assertEqual(analyze(c,a)['counts']['all_observed_sources_at_capacity'],1)

    def test_query_receipt_maps_to_eligible_entry_and_missing_remains_unknown(self):
        row = dict(atom=3, receipt={}, location=None)
        self.assertEqual(entry_sources(dict(anchors=[], query=[row]), [3]), {0: row})
        self.assertEqual(entry_sources(dict(anchors=[], query=[row]), [2]), {})


if __name__ == '__main__': unittest.main()

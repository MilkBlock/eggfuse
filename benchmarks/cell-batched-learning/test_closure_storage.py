import copy
import unittest
from closure_storage import classify


class ClosureStorage(unittest.TestCase):
    def setUp(self):
        self.storage = dict(components=[dict(shape=0, frames=[7], signals=[99, 100])],
                            shapes=[dict(signals=[[dict(frame=0, op=0)], []])])
        self.frames = [dict(cell=7, facts=[dict(op=0, owned=True, hidden=False)])]

    def test_visible_site_and_export_without_local_site(self):
        c = classify(self.storage, self.frames)
        self.assertEqual(c['live_owned_dispatch_sites'], 1)
        self.assertEqual(c['symbols_without_live_owned_site'], 1)
        self.assertEqual(c['composition_positions_without_source_frame'], 0)

    def test_hidden_fact_is_still_a_maintenance_obligation(self):
        self.frames[0]['facts'][0]['hidden'] = True
        c = classify(self.storage, self.frames)
        self.assertEqual(c['live_owned_dispatch_sites'], 1)
        self.assertEqual(c['symbols_with_only_hidden_owned_sites'], 1)

    def test_retired_source_leaves_static_sites(self):
        c = classify(self.storage, [])
        self.assertEqual(c['composition_positions_without_source_frame'], 1)
        self.assertEqual(c['absent_or_unowned_dispatch_sites'], 1)
        self.assertEqual(c['symbols_without_live_owned_site'], 2)

    def test_unbound_symbol_does_not_dispatch(self):
        self.storage['components'][0]['signals'][0] = None
        c = classify(self.storage, self.frames)
        self.assertEqual(c.get('static_dispatch_sites', 0), 0)

    def test_reject_duplicate_instance_positions(self):
        self.storage['components'].append(copy.deepcopy(self.storage['components'][0]))
        with self.assertRaises(ValueError):
            classify(self.storage, self.frames)

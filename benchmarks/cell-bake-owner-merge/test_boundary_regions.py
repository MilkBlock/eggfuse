import copy
import unittest
from boundary_regions import census


def fixture():
    # Root 7 is foreign. Root (3, slot 0) is the source's native result.
    native = (3 << 32) + 1
    return {'ownership_storage': {
        'components': [{'id': 2, 'shape': 0, 'frames': [3], 'frame_codes': [0],
                        'signals': [7, 7, native], 'roots': [7, 7, native]}],
        'shapes': [{'programs': [0], 'ports': [[0, 1, 2]],
                    'signals': [[{'frame': 0, 'op': 0}], [{'frame': 0, 'op': 1}], [{'frame': 0, 'op': 0}]]}],
        'programs': [{'native': {'0': 2}}], 'operators': [[4, 5]]},
        'ownership_query_work': {'boundary_live': 2},
        'graph_fields': [['ownership.boundaries', 80]], 'graph_owned_teardown_bytes': 1000}


class BoundaryRegions(unittest.TestCase):
    def test_foreign_aliases_share_component_record_but_keep_both_operators(self):
        result = census(fixture())
        self.assertEqual(result['boundary_signals'], 2)
        self.assertEqual(result['component_root_records'], 1)
        self.assertEqual(result['replay']['returned_symbol_routes'], 2)
        self.assertEqual(result['replay']['static_symbol_checks'], 3)

    def test_retired_native_origin_remains_a_boundary(self):
        x = fixture()
        x['ownership_storage']['components'][0]['frames'] = [8]
        x['ownership_query_work']['boundary_live'] = 3
        result = census(x)
        self.assertEqual(result['component_root_records'], 2)
        self.assertEqual(result['replay']['returned_symbol_routes'], 3)

    def test_unbound_positions_do_not_invent_routes(self):
        x = fixture()
        x['ownership_storage']['components'][0]['roots'][1] = None
        x['ownership_storage']['components'][0]['signals'][1] = None
        x['ownership_query_work']['boundary_live'] = 1
        result = census(x)
        self.assertEqual(result['replay']['empty_operator_cases'], 1)

    def test_boundary_accounting_is_mandatory(self):
        x = fixture()
        x['ownership_query_work']['boundary_live'] = 1
        with self.assertRaisesRegex(ValueError, 'runtime counter'):
            census(x)

    def test_duplicate_source_identity_is_rejected(self):
        x = fixture()
        c = copy.deepcopy(x['ownership_storage']['components'][0])
        c['id'] = 9
        x['ownership_storage']['components'].append(c)
        with self.assertRaisesRegex(ValueError, 'multiple component'):
            census(x)


if __name__ == '__main__':
    unittest.main()

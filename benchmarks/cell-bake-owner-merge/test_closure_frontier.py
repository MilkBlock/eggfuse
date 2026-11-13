import copy
import unittest
from closure_frontier import census


def fixture(bindings):
    return {'ownership_storage': {
        'programs': [{'native': {'0': 0}}],
        'shapes': [{'programs': [0], 'ports': [[0]], 'signals': [[], []]}],
        'components': [dict(id=i, shape=0, frames=[i+1],
                            signals=[((i+1)<<32)+1, value],
                            roots=[((i+1)<<32)+1, value]) for i, value in enumerate(bindings)]}}


class FrontierTests(unittest.TestCase):
    def test_shared_producer_is_not_exclusively_absorbed(self):
        x=census(fixture([None, (1<<32)+1, (1<<32)+1]))
        self.assertEqual(x['counts']['shared_producers'], 1)
        self.assertEqual(x['counts']['candidate_regions'], 3)
        self.assertEqual(x['counts']['cross_component_slots'], 2)
        self.assertEqual(x['counts']['shared_native_ports'], 1)
        self.assertEqual(x['counts']['exclusively_referenced_ports'], 0)

    def test_shared_source_can_have_exclusive_port_slices(self):
        x=fixture([None, (1<<32)+1, (1<<32)+2])
        storage=x['ownership_storage']
        storage['programs'][0]['native']['1']=1
        storage['shapes'][0]['ports']=[[0,1]]
        storage['shapes'][0]['signals'].append([])
        for i,c in enumerate(storage['components']):
            value=c['signals'].pop()
            c['signals'].extend([((i+1)<<32)+2,value])
            c['roots']=list(c['signals'])
        result=census(x)['counts']
        self.assertEqual(result['shared_producers'],1)
        self.assertEqual(result['shared_native_ports'],0)
        self.assertEqual(result['exclusively_referenced_ports'],2)
        self.assertEqual(result['candidate_regions'],3)

    def test_exclusive_chain_forms_only_a_candidate(self):
        x=census(fixture([None, (1<<32)+1, (2<<32)+1]))
        self.assertEqual(x['counts']['candidate_regions'], 1)
        self.assertEqual(x['counts']['largest_candidate_region'], 3)

    def test_cycles_are_not_an_ownership_forest(self):
        x=census(fixture([(2<<32)+1, (1<<32)+1]))
        self.assertEqual(x['counts']['exclusive_cycle_nodes'], 2)
        self.assertEqual(x['counts']['candidate_regions'], 2)

    def test_union_roots_do_not_invent_provenance(self):
        x=fixture([None, 777])
        x['ownership_storage']['components'][1]['roots'][1]=(1<<32)+1
        result=census(x)['counts']
        self.assertEqual(result.get('cross_component_slots',0), 0)
        self.assertEqual(result['unknown_origin'], 1)

    def test_foreign_result_and_invalid_snapshot(self):
        x=fixture([None, (1<<32)+1])
        x['ownership_storage']['components'][0]['signals'][0]=999
        x['ownership_storage']['components'][0]['roots'][0]=999
        self.assertEqual(census(x)['counts']['unconfirmed_origin'], 1)
        bad=copy.deepcopy(x)
        bad['ownership_storage']['components'][0]['roots'].pop()
        with self.assertRaises(ValueError): census(bad)
        bad=copy.deepcopy(x)
        bad['ownership_storage']['components'][1]['frames']=[1]
        with self.assertRaises(ValueError): census(bad)

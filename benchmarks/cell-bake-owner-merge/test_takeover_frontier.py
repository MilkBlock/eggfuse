import unittest
from takeover_frontier import census


def fixture():
    return {'graph_owned_teardown_bytes':1000,'retained_program_teardown_bytes':2000,
        'graph_fields':[['cells',200]],
        'source_storage':{'fact_lifecycle':{'frames':[
            {'cell':7,'completed':True,'retainers':1,'parent':None,'started_epoch':2,
             'facts':[{'op':0,'owned':True,'hidden':True,'born':2,'epoch':3}]}
        ]}},
        'ownership_storage':{'components':[
            {'shape':0,'frames':[7],'roots':[11,11,None]},
            {'shape':0,'frames':[8],'roots':[11,12,None]}],
            'shapes':[{'programs':[0],'signals':[[],[],[]]}],
            'programs':[{'fields':[[0,1]]}]}}


class FrontierTests(unittest.TestCase):
    def test_aliases_are_partitioned_without_counting_unbound_slots(self):
        r=census(fixture());c=r['counts']
        self.assertEqual((c['bound_symbols'],c['distinct_roots']), (4,2))
        self.assertEqual((c['same_component_repeated_roots'],c['cross_component_repeated_roots']), (1,1))
        self.assertEqual(r['oracle_duplicate_binding_payload_bytes'],32)

    def test_missing_source_and_hidden_fact_are_not_deleted(self):
        c=census(fixture())['counts']
        self.assertEqual(c['positions_without_source_storage'],1)
        self.assertEqual(c['hidden_owned_facts'],1)
        self.assertEqual(c['externally_retained_sources'],1)
        self.assertEqual(c['facts_with_source_lifecycle'],0)

    def test_scalar_fields_are_not_mistaken_for_template_only_rows(self):
        x=fixture();x['ownership_storage']['programs'][0]['fields'][0]=[0,None]
        c=census(x)['counts']
        self.assertEqual(c['scalar_bearing_owned_facts'],1)
        self.assertEqual(c['scalar_free_owned_facts'],0)

    def test_duplicate_addresses_and_incomplete_layouts_fail_closed(self):
        x=fixture();x['ownership_storage']['components'][1]['frames']=[7]
        with self.assertRaisesRegex(ValueError,'multiple component'):census(x)
        x=fixture();x['ownership_storage']['components'][0]['roots']=[11]
        with self.assertRaisesRegex(ValueError,'incomplete symbol'):census(x)
        x=fixture();x['source_storage']['fact_lifecycle']['frames']*=2
        with self.assertRaisesRegex(ValueError,'duplicate source'):census(x)


if __name__=='__main__':unittest.main()

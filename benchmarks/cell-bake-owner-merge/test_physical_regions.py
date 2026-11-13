import unittest
from physical_regions import census


def fixture():
    return {'source_storage': {'completed_regions': {
        'schema':'completed-regions/v1','source_record_bytes':56,'owner_record_bytes':80,
        'layouts':[{'template':1,'slots':[0],'ops':[2]}],
        'frames':[{'cell':i,'owner':0,'layout':0,'started_epoch':i,'slot_start':i-1,'fact_start':i-1} for i in (1,2)],
        'owners':[{'id':0,'sources':2,'slot_entries':3,'fact_entries':3,'live_facts':2}]},
        'fact_lifecycle':{'frames':[{'cell':i,'template':1,'started_epoch':i,'completed':True,
            'completed_storage':True,'facts':[{'op':2}],'retainers':int(i==1)} for i in (1,2)]}},
        'ownership_storage':{'components':[{'id':i,'frames':[i]} for i in (1,2)]}}


class PhysicalRegions(unittest.TestCase):
    def test_mixed_owner_and_holes_are_not_a_single_logical_region(self):
        c=census(fixture())['counts']
        self.assertEqual(c['physical_owners_spanning_logical_components'],1)
        self.assertEqual(c['slot_entries_outside_source_ranges'],1)
        self.assertEqual(c['external_source_readers'],1)

    def test_retired_fact_position_keeps_layout_without_inventing_a_fact(self):
        x=fixture();x['source_storage']['fact_lifecycle']['frames'][0]['facts']=[]
        x['source_storage']['completed_regions']['owners'][0]['live_facts']=1
        self.assertEqual(census(x)['counts']['fact_entries_in_source_ranges'],2)

    def test_overlapping_ranges_fail(self):
        x=fixture();x['source_storage']['completed_regions']['frames'][1]['slot_start']=0
        with self.assertRaisesRegex(ValueError,'overlapping'):
            census(x)

    def test_missing_source_or_wrong_epoch_fails(self):
        x=fixture();x['source_storage']['completed_regions']['frames'][0]['started_epoch']=9
        with self.assertRaisesRegex(ValueError,'metadata'):
            census(x)
        x=fixture();x['source_storage']['completed_regions']['frames'].pop()
        with self.assertRaisesRegex(ValueError,'inventory'):
            census(x)


if __name__=='__main__':
    unittest.main()

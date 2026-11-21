"""Validate byte equality, identical logical frontier and symmetric actual-work accounting."""
import json
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
def verify():
    data=json.loads((HERE/'results.json').read_bytes())
    assert set(data)=={'3mm','sum-bits'}
    for case,arms in data.items():
        old=arms['span'];new=arms['sparse']
        original_file='results.json' if case=='3mm' else 'smoke.json'
        previous=json.loads((HERE.parent/'compound-family-ports'/original_file).read_bytes())[case]['compound']
        assert 'family' in arms['fault']
        for name,row in [('span',old),('sparse',new)]:
            assert all(row['checks'].values()) and len(row['ms'])==4 and median(row['ms'])==row['median_ms']
            f=row['stats'];z=row['region_work']
            for key in ('rhs','commits','physical','root_parents','root_ids','nested_ids','cells','state_sha','birth_digest','visible_digest','visible','expanded','raw_issue_sha','group_visible','external_roots','no_commit','no_visible','fept','strict_fept','rules'):
                assert row[key]==old[key]==previous[key],(case,name,key)
            for key in ('prototypes','absent','stale','private_rows','candidate_bound','actions','keys_issued','receiver_public_decodes','receiver_pairs','sender_marginal_rows','wire_bytes'):
                assert f[key]==old['stats'][key]==previous['stats'][key]
            assert row['wire_sha']==old['wire_sha'] and len(row['wire_sha'])==64
            assert z['materialized_regions']==f['prototypes']-f['absent']-f['stale']
            assert row['paid_decisions']==row['explicit_packets']+z['keys_absent']+z['no_fresh_region']
            assert row['strict_packets']==row['explicit_packets']+f['absent']+f['stale']
            assert row['paid_fept']==row['visible']/row['paid_decisions']
            assert row['all_query_tests']==z['keys_probed']+z['epoch_checks']+z['binary_steps']
            assert row['all_query_events_with_setup']==row['explicit_packets']+row['all_query_tests']+z['construction_key_updates']+f['sender_marginal_rows']
            assert z['model_online_encodes']==0 and z['model_table_lookups']==z['model_port_requests']==old['region_work']['model_port_requests']
        assert new['region_work']['skipped_missing_regions']==old['region_work']['keys_absent']
        assert new['region_work']['skipped_stale_regions']==old['region_work']['no_fresh_region']
        assert new['region_work']['left_builds']>0 and new['region_work']['left_reuses']>0
        assert new['region_work']['keys_probed']<old['region_work']['keys_probed']
        assert new['region_work']['peak_payload']<=8<<20
if __name__=='__main__':
    verify();print('Verified byte-identical ordered compound packets, frozen signed choices, complete native source parity, both logical and actually executed probe counts.')

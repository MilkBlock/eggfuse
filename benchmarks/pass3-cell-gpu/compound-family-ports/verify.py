from pathlib import Path
from statistics import median
import json
HERE=Path(__file__).resolve().parent
def verify():
    for filename,case in [('results.json','3mm'),('smoke.json','sum-bits')]:
        v=json.loads((HERE/filename).read_bytes())[case]
        prev=json.loads((HERE.parent/'generative-pair-families'/filename).read_bytes())[case]
        base=v['wide'];second=v['compound'];z=second['scalar']
        assert z['admitted']>0 and z['planned']==z['admitted']+z['fallback']
        assert z['compound_packets']>0 and z['receiver_computed']>0 and z['sender_computed']>0
        assert z['compound_bytes']==72*z['compound_packets']+8*z['compound_keys']
        assert base['stats']['wire_bytes']==prev['wide']['stats']['wire_bytes']
        for name in ('ordinary','wide','compound'):
            row=v[name];m=row['stats']
            for k in ('checks','rhs','commits','physical','cells','root_ids','nested_ids','root_parents','children','multi_winners','single_winners',
                      'state_sha','multi','visible','births','birth_digest','visible_digest','expanded','raw_issue_sha','child_selected','checked_parents'):
                assert row[k]==v['ordinary'][k]==prev['off'][k],(case,name,k)
            assert all(row['checks'].values()) and m['private_rows']+row['external_roots'][1]==row['expanded']
            assert m['receiver_pairs']==m['candidate_bound'] and m['receiver_pairs']>=m['private_rows']
            assert m['wire_bytes']==72*m['actions']+4*(m['keys_issued']+row['scalar']['compound_keys'])
            assert row['explicit_packets']==sum(row['external_roots'])+row['child_selected']+m['actions']
            if 'ms' in row:assert len(row['ms'])==4 and median(row['ms'])==row['median_ms']
        for k in ('group_accepted','group_visible','external_roots'):assert base[k]==second[k]
        assert second['stats']['receiver_pairs']<base['stats']['receiver_pairs']
        assert second['stats']['private_rows']==base['stats']['private_rows']
        assert 'family' in v['fault']
if __name__=='__main__':
    verify();print('Verified complete regenerated learned stream, physical origins, compiled two-key wire, checked bounds and native arithmetic-key corruption controls.')

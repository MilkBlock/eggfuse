"""Recheck the regenerated oracle stream, late visibility, explicit costs and source bounds."""
import json
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
MATCH=('checks','rhs','commits','physical','cells','root_ids','nested_ids','root_parents','children','multi_winners',
       'single_winners','state_sha','multi','births','visible','birth_digest','visible_digest','expanded',
       'raw_issue_sha','child_selected','child_decisions','checked_parents')
def verify(x):
    for case,arms in x.items():
        base=arms['off'];assert all(base['checks'].values()) and 'family' in arms['fault']
        for k in ('off','small','wide'):
            r=arms[k];m=r['stats'];limit=64 if k=='small' else 256
            assert all(r[f]==base[f] for f in MATCH)
            assert m['receiver_pairs']==m['candidate_bound']
            assert m['receiver_pairs']<=m['actions']*limit and m['private_rows']<=m['receiver_pairs']
            assert r['external_roots'][1]+m['private_rows']==base['external_roots'][1]
            assert m['wire_bytes']==72*m['actions']+4*m['keys_issued']
            assert r['strict_packets']==r['explicit_packets']+m['absent']+m['stale']
            assert r['explicit_packets']==sum(r['external_roots'])+r['child_selected']+m['actions']
            assert r['matched_lower_bound']==sum(r['external_roots'])+r['child_selected']+m['matched_min_packets']
            assert r['fept']==r['visible']/r['explicit_packets'] and r['strict_fept']==r['visible']/r['strict_packets']
            assert r['fept']<=r['matched_ceiling']
            assert r['no_commit']<=m['actions'] and r['no_visible']<=m['actions']
            if k!='off':
                assert r['examples'] and m['private_rows']>0 and m['receiver_public_decodes']>0
                assert sum(v[3] for v in r['rules'].values())==m['private_rows']
            if 'ms' in r:
                assert len(r['ms'])==4 and median(r['ms'])==r['median_ms']
        assert arms['wide']['stats']['private_rows']==arms['small']['stats']['private_rows']
if __name__=='__main__':
    results=json.loads((HERE/'results.json').read_bytes());smoke=json.loads((HERE/'smoke.json').read_bytes())
    assert set(results)=={'3mm','deriche'} and set(smoke)=={'sum-bits'}
    verify(results);verify(smoke)
    print('Verified real regenerated raw multi-parent stream, source and constructor origins, bounded family actions, corrupt extents and oracle bounds.')

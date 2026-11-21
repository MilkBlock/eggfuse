"""Verify that real external literals are removed and the independent receiver reconstructs all parents."""
import json
from hashlib import sha256
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
def verify():
    model=json.loads((HERE/'policy.json').read_bytes())
    assert model['raw_sha256']==sha256((HERE/'donors.json').read_bytes()).hexdigest()
    train=json.loads((HERE/'donors.json').read_bytes());assert set(train)==set(model['donors'])=={'sum-bits','dot-product'}
    pos=sum(n for case in train.values() for _,y,n in case['capture']['examples'] if y)
    n=sum(case['capture']['stats']['groups'] for case in train.values())
    assert (pos,n-pos)==(model['positive'],model['negative'])
    d=json.loads((HERE/'results.json').read_bytes());assert set(d)=={'conjugate-gradient','3mm'}
    work=json.loads((HERE/'work.json').read_bytes())
    for case,arms in d.items():
        b=arms['off']
        assert 'bucket' in arms['fault']
        for name in ('off','group','all'):
            r=arms[name];s=r['stats'];g=r['outcomes']
            assert all(r['checks'].values()) and len(r['ms'])==4 and r['median_ms']==median(r['ms'])
            for key in ('rhs','root_parents','root_ids','nested_ids','children','cells','visible','birth_digest','visible_digest','multi_winners','single_winners','births','commits','physical','multi','state_sha'):
                assert r[key]==b[key],(case,name,key)
            assert r['external'][0]==b['external'][0] and s['declared_lanes']+r['external'][1]==b['external'][1]
            assert s['groups']+s['small_or_large']+s['gate_reject']==s['score_calls']
            assert s['receiver_postings']==s['declared_lanes']
            assert 2*s['groups']<=s['declared_lanes']<=64*s['groups'] and s['wire_bytes']==72*s['groups']
            assert r['external_packets']==sum(r['external'])+r['selected_children']+s['groups']
            assert r['strict_decisions']==sum(r['external'])+r['selected_children']+s['score_calls']
            assert r['fept']==r['visible']/r['external_packets'] and r['strict_fept']==r['visible']/r['strict_decisions']
            w=work[case][name]
            assert w['all_decisions']==w['single_score_inputs']+sum([w['explicit_multi_residual'],w['group_signature_opportunities'],w['all_child_decisions']])
            assert w['receiver_table_decodes']==s['receiver_decoded'] and w['receiver_verified_group_lanes']==s['declared_lanes']
            assert w['visible_per_all_decisions']==r['visible']/w['all_decisions']
            if name!='off':
                assert s['groups']>0 and g['winning_lanes']>0 and 0<=g['visible_births']<=r['visible']
                assert g['no_commit']<=s['groups'] and r['fept']>b['fept']
        assert 0<arms['group']['stats']['groups']<arms['all']['stats']['groups']
if __name__=='__main__':
    verify();print('Verified donor-frozen predictions, independent regenerated parent stream, ordered graph and birth origins, bounded negative controls and charged action denominators.')

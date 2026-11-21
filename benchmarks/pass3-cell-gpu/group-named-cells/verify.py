"""Check workload/source invariants, sealed-lane authority, matched budgets and negative controls."""
import argparse,json,sys
from hashlib import sha256
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'pair-source-frontier'))
from evidence import checked


def verify(folder):
    runs=checked(folder,('results.json',),('conjugate-gradient','3mm'))
    for case,arms in runs.items():
        assert set(arms)=={'vanilla','off','pooled','named','group'}
        base=arms['pooled']['staging']
        for name in ('pooled','named','group'):
            r=arms[name];s=r['staging']
            for field in ('requested','clipped','granted','preconstructed','fresh','committed','offers','peak_private_bytes',
                          'peak_slots','header_capacity_bytes','private_payload_capacity_bytes'):
                assert s[field]==base[field]
            assert s['used']==s['payload_identity']==s['sampled_payloads'] and s['granted']==s['unused']+s['used']
            assert s['fresh']==s['fallback']+s['used']
            assert s['offers_before_first_verify']==s['offers'] and s['slots_before_first_verify']==s['granted']
            assert r['score_digest']==arms['off']['score_digest']
            assert r['wave']['sealed_multi']==arms['off']['wave']['sealed_multi']
            assert r['wave']['sealed_single']==arms['off']['wave']['sealed_single']
        g=arms['group']['staging'];n=arms['named']['staging']
        assert n['used']<g['used']==g['redeemed']==base['used']
        assert g['authorized_lanes']>=g['redeemed']
        assert g['redeemed_beyond_named']>=g['used']-n['used']
        assert g['foreign_denials']==g['duplicate_denials']==0
        assert 0<g['peak_bitmap_bytes']<=g['bitmap_bytes'] and g['group_pages']>0
    faults=json.loads((folder/'faults.json').read_bytes())
    assert set(faults)=={'none','stale','foreign','duplicate','withheld'}
    first=faults['none']
    for mode,r in faults.items():
        assert r['aligned'] and all(r['checks'].values()) and r['rhs']==r['neural_rhs']
        for k in ('rhs','cells','multi','physical','root_parents','root_ids','nested_ids','state_sha','raw','single_winners','multi_winners','children'):
            assert r[k]==first[k]
        c=r['staging']
        if mode in ('stale','foreign','withheld'):
            key={'stale':'stale_named','foreign':'foreign_denials','withheld':'missing_named'}[mode]
            assert c['used']==0 and c[key]>0 and c['fallback']==c['fresh']
        if mode=='duplicate':assert c['used']==c['duplicate_denials']==first['staging']['used']>0
    manifest=json.loads((folder/'manifest.json').read_bytes())
    assert manifest['head']=='run/coverage' and manifest['cap']==8192 and manifest['seed']==1703
    assert manifest['compiled_voucher_sha256']==sha256((HERE/'group.rs').read_bytes()).hexdigest()
    assert manifest['policy_sha256']==sha256((HERE.parent/'speculative-allocation-policy/policy.json').read_bytes()).hexdigest()
    return runs

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder',type=Path,nargs='?',default=HERE)
    print('Verified group-authorized private payloads on',len(verify(p.parse_args().folder)),
          'held-out Pass 3 sources and four voucher controls')

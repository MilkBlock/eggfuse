"""Check measured online ranking choices, corruption behavior and exact source endpoints."""
from pathlib import Path
import json
HERE=Path(__file__).resolve().parent


def verify(folder):
    evidence=json.loads((folder/'controls.json').read_bytes())
    assert set(evidence)=={'sum-bits','dot-product'}
    for name,arms in evidence.items():
        assert set(arms)=={'legacy','first','zero','reverse','hidden','foreign','withheld','stale','zero-cap'}
        old=arms['legacy'];first=arms['first']['staged']
        for mode,r in arms.items():
            assert all(r['checks'].values()) and r['aligned'] and r['rhs']==r['neural_rhs'] and r['direct_cells']*100>=98*r['fresh']
            for k in ('single_winners','multi_winners','cells','state_sha','root_parents','root_ids','nested_ids','rhs','direct_cells','raw','multi','commits','physical','children'):
                assert r[k]==old[k]
            s=r['staged']
            assert s['fresh']==r['root_allocated']==s['used']+s['fallback']
            assert s['used']==s['payload_identity'] and s['granted']==s['used']+s['unused']
            assert s['offers_after_first_verify']==s['slots_after_first_verify']==0
            if mode!='legacy':
                q=r['rank'];assert q['scored']<=q['lanes']==s['offers'] and q['selected']==q['before_verifier']
                assert q['fresh_lanes']==s['fresh'] and 0<=q['selected_fresh']<=q['oracle_fresh']
                assert q['repeated_fresh']==q['unlisted_fresh']==0
            if mode in ('zero','first'):
                assert s['used']==old['staged']['used']==q['first_fresh'] and not q['beyond_first_chosen']
            elif mode in ('reverse','hidden'):
                l,h=r['independent_tie_bounds']
                assert l<=s['used']==q['selected_fresh']<=h
                assert q['scored']>0 and q['beyond_first_chosen']>=q['beyond_first_fresh']>0
            elif mode in ('stale','withheld','foreign'):
                f={'stale':'stale_named','withheld':'missing_named','foreign':'parent_mismatch'}[mode]
                assert not s['used'] and s[f]==q['selected_fresh']>0
            elif mode=='zero-cap':
                assert s['granted']==q['selected']==0 and s['fresh']>0
                assert r['hist_sha256']==arms['first']['hist_sha256']
        assert arms['hidden']['rank']==arms['reverse']['rank']
        assert [a['staged']['granted'] for k,a in arms.items() if k!='zero-cap']==[first['granted']]*(len(arms)-1)
    return evidence

if __name__=='__main__':print('Verified live whole-Run candidate ranking and physical backing, signed roots, complete source ledgers and stale/withheld/foreign controls on',len(verify(HERE)),'Pass 3 programs')

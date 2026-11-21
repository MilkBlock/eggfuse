"""Check the strict denominator, internal evidence, compile-time library and fixed-RSS level."""
import json
from pathlib import Path
from statistics import median
from math import isclose

HERE=Path(__file__).resolve().parent
def read(name):
    return json.loads((HERE/name).read_bytes())


def verify():
    data=read("results.json");extra=read("completed-producers.json");rss=read("rss.json")
    links=read("links.json")
    gold=read("../token-constructor-births/results.json")
    for c,case in data.items():
        ref=case['arms']['leaf'];orig=gold[c]
        assert ref['visible']==orig['retention']['original_visible_per_committed_root']['births']
        assert ref['packets']==orig['per_issued_root']['denominator']+orig['child_packets']['selected']
        for n,q in case['arms'].items():
            assert all(q['checks'].values()) and q['aligned'] and q['median_ms']==median(q['ms'])
            for field in ('rhs','commits','physical','root_ids','nested_ids','children','state_sha','root_parents','end_digest','visible','births','birth_digest','selected_children'):
                assert q[field]==ref[field],(c,n,field)
            assert q['packets']==sum(q['emitted'])+q['selected_children']
            assert isclose(q['yield_per_packet'],q['visible']/q['packets'])
            if n!='leaf':
                st=q['production']
                assert st['source_commits']==st['no_score_inputs']==st['actual_internal']==ref['packets']-q['packets']
                assert st['audit_score_inputs']==0
                assert st['source_commits']==st['direct_spine_lookups']
                assert st['two_with_internal_parent']<=st['source_commits']
        for n,q in extra[c].items():
            assert q['packets']==ref['packets']-q['counts']['source_commits']
            assert all(q['checks'].values()) and q['state_sha']==ref['state_sha'] and q['visible']==ref['visible']
        for n,t in links[c].items():
            res=extra[c][n] if n in extra[c] else case['arms'][n]
            assert t['internal_source_commits']==ref['packets']-res['packets']
            assert t['visible']==ref['visible'] and t['births']==ref['births']
            credited=t['increment_from_internal']
            assert sum(m for _,m in credited)==t['credited_external_roots']
            assert sum(k*m for k,m in credited)==t['actual_internal_visible_excluding_paid_child']
        r=rss[c]
        for name,obs in r['arms'].items():
            assert name in case['arms'] and len(obs)==3
            for s in obs:
                pts=s['trace'];start=pts[0][1];assert max(b for _,b in pts)==s['peak_kib']
                for key,h in [('absolute',r['levels_kib'][0]),('increment',start+r['levels_kib'][1])]:
                    t=next((t for t,b in pts if b>=h),None)
                    assert s['crossings'][key]==['unreached' if t is None else 'left' if start>=h else 'reached',t]
    print("Verified strictly named releases, final constructor origins and independent sampled RSS crossings.")


if __name__=='__main__':
    verify()

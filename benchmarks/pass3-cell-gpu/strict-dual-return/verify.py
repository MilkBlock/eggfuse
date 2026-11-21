from pathlib import Path
from statistics import median
import json
from freeze import frozen
HERE=Path(__file__).resolve().parent
def verify():
    assert frozen()==json.loads((HERE/'template.json').read_bytes())
    x=json.loads((HERE/'results.json').read_bytes())
    previous=json.loads((HERE.parent/'strict-composition-opportunities/results.json').read_bytes())
    pair=next(r for r in json.loads((HERE.parent/'strict-composition-opportunities/catalog.json').read_bytes())['pairs'].values()
              if r['shape']==[501,286,1,[[0,'op',6],[1,'op',5]],2])
    rss=json.loads((HERE/'rss.json').read_bytes())
    for case,arms in x.items():
        base=arms['ordinary'];on=arms['dual'];c=on['dual'];n=on['confirmed']
        assert c['typed_returns']>=2*n and c['both_returns']==c['captured']==c['private_created']==c['actual_commits']==c['protected_anchors']==n>0
        assert c['direct_reads']==2*n and c['upper_bound_reads']==n
        assert c['audited_external_lanes']>0 and base['external']-on['external']==n and c['bypassed_reverse']>0
        assert c['producer_tags']>=c['signed_commits'] and c['signed_commits']>=n
        assert n==pair['heldout_counts'][case] and c['count_activations']>=n
        assert on['outstanding']==on['internal_child_visible_births']==0
        assert base['emitted'][0]==on['emitted'][0] and base['emitted'][1]==on['emitted'][1]+n
        assert base['state_sha']==previous[case]['reference']['state_sha']
        for mode,v in arms.items():
            assert all(v['checks'].values())
            for k in ('rhs','runs','state_sha','root_parents','ordered_winners','physical_ordinals','nested_ids','cells','single','births','final','retained','all_child_decisions','selected_children'):
                assert v[k]==base[k],(case,mode,k)
            assert v['external']==sum(v['emitted'])+v['selected_children'] and v['fept']==v['retained']/v['external']
            if mode in ('wrong_version','no_unique'):
                assert v['confirmed']==0 and v['external']==base['external'] and v['dual']['captured']==0
                assert v['dual']['unavailable' if mode=='wrong_version' else 'multiplicity']==n
            else:assert len(v['ms'])==4 and median(v['ms'])==v['median_ms']
        r=rss[case];assert r['reference']==base['state_sha'] and len(r['rows']['dual'])==len(r['rows']['ordinary'])==4
        for name,rows in r['rows'].items():
            for v in rows:
                t=v['trace_kib'];assert v['entry_kib']==t[0][1] and v['peak_kib']==max(row[1] for row in t)
                for k,delta in r['threshold_growth_kib'].items():
                    assert v['t_growth_ms'][k]==next((o[0]/1000 for o in t if o[1]-t[0][1]>=delta),None)
                    first='left' if t[0][1]>=r['calibration_entry_kib']+delta else next((o[0]/1000 for o in t if o[1]>=r['calibration_entry_kib']+delta),None)
                    assert v['t_absolute_ms'][k]==first
    print('Verified preissued dual-return variants, independently named live child parents, excluded ordinary pivot branches, exact source/birth identities, faults, complete-inference and fresh-process RSS.')
if __name__=='__main__':verify()

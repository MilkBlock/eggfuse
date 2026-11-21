from pathlib import Path
import json
from statistics import median
from freeze import frozen
HERE=Path(__file__).resolve().parent
def verify():
    assert frozen()==json.loads((HERE/'template.json').read_bytes())
    v=json.loads((HERE/'results.json').read_bytes());rss=json.loads((HERE/'rss.json').read_bytes())
    known=json.loads((HERE.parent/'strict-composition-opportunities/catalog.json').read_bytes())['pairs'][frozen()['pair_shape']]['heldout_counts']
    for case,arms in v.items():
        base=arms['ordinary'];on=arms['carried'];n=on['confirmed'];proof=on['details'];z=proof['counts']
        assert base['possible']==known[case] and 0<=n<=base['possible']
        assert z['protected']==z['private_roots']==z['confirmed']==n and proof['outstanding']==0
        assert z['prefix_preempted']==n and base['external']-on['external']>=n
        assert z['count_updates']>=n and z['tags']>=z['producers']>=z['actual_outputs']
        assert sum(proof['terminal_degree_bins'])==z['public_counts']==sum(proof['reference_live_degree_bins'])
        assert sum(z[k] for k in ('missing','stale','wrong_table','atom_guards','old_binding','not_unique','protected'))==z['release_attempts']
        assert sum(proof['guard_failure_atoms'])==z['atom_guards']
        assert sum(on['direct_retained'].values())<=sum(on['direct_new'].values())
        assert sum(on['ordinary_alternatives'].values())==on['possible']
        for nrow,r in arms.items():
            assert all(r['checks'].values())
            for k in ('rhs','runs','state_sha','root_parents','nested','cells','ordered','source_births','births','roots','final','single','retained','selected_children','all_child_decisions','possible_source_digest','ordinary_alternatives'):
                assert r[k]==base[k],(case,nrow,k)
            assert r['external']==sum(r['emitted'])+r['selected_children'] and r['fept']==r['retained']/r['external']
            if nrow in ('wrong_version','no_unique'):assert r['confirmed']==0 and r['external']==base['external']
            else:assert len(r['ms'])==4 and median(r['ms'])==r['median_ms']
        ref=rss[case]
        assert ref['reference']==base['state_sha']
        for rows in ref['rows'].values():
            assert len(rows)==4
            for obs in rows:
                t=obs['trace_kib'];assert t[0][1]==obs['entry_kib'] and max(p[1] for p in t)==obs['peak_kib']
                for key,delta in ref['threshold_growth_kib'].items():
                    assert obs['t_growth_ms'][key]==next((us/1000 for us,kib in t if kib-t[0][1]>=delta),None)
    print('Verified all source Runs and original constructor/child identities, actual suppressed explicit packets, certified-prefix and multiplicity controls, and measured common RSS crossings.')
if __name__=='__main__':verify()

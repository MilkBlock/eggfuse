"""Check measured registration, causal retirement and independently verified support counts."""
import json
from pathlib import Path


def verify(folder=None):
    root=Path(folder) if folder else Path(__file__).resolve().parent
    def read(name):return json.loads((root/name).read_text())
    real,supports,probes=map(read,('retirement.json','supports.json','union-probes.json'))
    provenance=read('source-audit.json')
    assert provenance.keys()==real.keys()
    for key,policies in provenance.items():
        for name,stats in policies.items():
            assert stats['verified_child_source_tickets']==real[key][name]['children']
            assert stats['exact_residual']==real[key][name]['exact']
            assert stats['stale_sources_checked']==real[key][name]['stale']
            assert stats['failed_parents_checked']==real[key][name]['orphan']
    visible=read('visibility.json')
    assert len(visible)==4 and all(len({tuple(v[:3]) for v in rows})==len(rows) for rows in visible.values())
    families=('sum-bits','dot-product','gemm-bias-relu','stable-argmax')
    assert len(real)==12 and len(supports)==len(probes)==8
    for n in families:
        for seed in (1703,1709):
            key=f'{n}/{seed}'
            test=real[f'{key}/observed']
            for run in [test]+([real[f'{key}/reject-parent']] if seed==1709 else []):
                whole,deps=run['batch'],run['dependencies']
                for arm in (whole,deps):
                    assert arm['source_aligned'] and arm['roots']+arm['children']+arm['exact']==arm['rhs']
                    assert len(arm['ms'])==6
                    assert arm['stale_hidden']+arm['stale_republished']==arm['stale']
                    assert arm['stale']+arm['orphan']+arm['collateral']==len(arm['invalidations'])
                    for issue,_,status,at,_ in arm['invalidations']:
                        assert at>=issue and (status!=3 or at>issue)
                assert whole['roots']==deps['roots'] and deps['collateral']==0
                if run['unrelated_child_winner_differences']==0:
                    assert deps['children']-whole['children']==run['collateral_that_would_win']
            s=supports[key];shape=s['shape'];assert s['mps'] and s['independent_oracle']
            assert shape['checked_post_rebuild_visibility'] and shape['constructor_facts']>shape['known_multi_support']>=0
            assert shape['published_constructor_records']>=shape['constructor_facts']
            assert shape['published_multi_support']>=shape['known_multi_support']
            assert shape['learned_parent_edges']==test['dependencies']['children']
            assert shape['proofs']==test['dependencies']['children']+test['dependencies']['roots']
            b,d,c=[s['policies'][arm] for arm in ('batch','dependencies','supports')]
            for arm in [b,d,c]:
                assert arm['retired_proofs']+arm['surviving_proofs']==shape['proofs']*s['exhaustive_single_root_withdrawals']
                assert len(arm['full_stream_counterfactual_group_ms'])==12
            assert b['retired_proofs']>=d['retired_proofs']==c['retired_proofs']
            assert c['unsupported_constructor_facts']==d['unsupported_constructor_facts']
            assert c['source_rechecks']==c['dirty_memberships']==0 and d['source_rechecks']>=d['dirty_memberships']
            assert d['dirty_memberships']==c['unsupported_constructor_facts']+c['immediately_retained_alternatives']
            for example in s['examples']:
                assert set(example['lost_rhs']).isdisjoint(example['surviving_rhs'])
            challenge=probes[key];assert challenge['source_aligned'] and challenge['wrong_sources_accepted']==0
            assert challenge['offered_winners']==shape['learned_parent_edges']
            for e in challenge['examples']:
                assert e['valid_row']!=e['wrong_row'] and e['claimed_ticket']!=e['wrong_ticket'] and e['release']>e['issue']
    print('Verified full Pass 3 pending retirement, typed-source challenges and separate whole-stream constructor supports.')


if __name__=='__main__':verify()

"""Validate attribution, coverage denominators, timing repetitions and isolation for the atlas."""
import json
from pathlib import Path


def check():
    root=Path(__file__).resolve().parent
    def read(name):return json.loads((root/name).read_text())
    feedback,guard,bootstrap=map(read,('feedback-results.json','guard-results.json','bootstrap-results.json'))
    compositions,budgets,waves=map(read,('composed-ceilings.json','leaf-budgets.json','wave-results.json'))
    exchange=read('exchange-results.json')
    targets=read('compound-targets.json')
    assert len(targets)==6 and sum(v['split']=='train' for v in targets.values())==4
    assert set(targets).isdisjoint(compositions)
    assert all(v['checked_spine_inputs']>0 and v['paths']['2']>0 for v in targets.values())
    for name,leaf,composed in [('sum-bits',181,246),('dot-product',161,207),('gemm-bias-relu',154,222),('stable-argmax',117,166)]:
        data=compositions[name];example=data['example_chain']
        assert all(c['producer_rhs']==p['rhs_ordinal'] and p['source_run']<c['source_run'] for p,c in zip(example,example[1:]))
        assert data['budgets']['2']['composed']['covered']==composed
        for n,b in data['budgets'].items():
            assert b['leaf']==budgets[name]['budgets'][str(int(n)//2)]['reference_winners']
            assert b['leaf']<=b['composed']['covered']<=data['reachable_distinct']
            assert b['composed']['optimal']
        assert leaf==data['budgets']['2']['leaf']
        for seed in (1703,1709):
            key=f'{name}/{seed}'
            isolated=read(f'isolated-{seed}.json')[name]
            assert isolated['neural_only']['actual_rhs']==0 and isolated['neural_only']['first_schedule_or_count_difference']==1
            assert all(len(v['opened'])==6 for v in isolated.values())
            for study,reps in [(feedback,12),(guard,8)]:
                for arm,v in study[key].items():
                    assert v['semantic_exact'] and len(v['ms'])==reps
                    if 'waves' not in v:continue
                    assert v['committed']+v['exact_residual']==data['rhs'] and v['runs']==data['runs']
                    assert sum(sum(w['committed']) for w in v['waves'])==v['committed']
                    assert v['work']['exact_seeds_skipped']==sum(w['accepted'] for w in v['waves'])
                    assert v['free_roll_discrete_differences']==0 and v['max_latent_difference']<.002
            assert guard[key]['blind-guard']['wave2_reclaims']==guard[key]['ids-guard']['wave2_reclaims']==0
            assert data['neural_roots'][str(seed)]['neural_submitted']==feedback[key]['ids']['committed']
            a,b,c=[bootstrap[f'{key}/{n}'] for n in ('none','empty-lhs','full')]
            assert a['first_divergence']==1 and a['exact_rhs']==0 and b['first_divergence']==3
            assert b['exact_rule_ids']==[375,574] and b['exact_rhs']==2
            assert c['first_divergence'] is None and c['neural_rhs']==feedback[key]['ids']['committed']
            for arm,v in exchange[key].items():
                assert len(v['ms'])==8 and v['verified'] and v['runs']==data['runs']
                if arm!='exact':assert v['neural_committed']==c['neural_rhs']
            if key not in waves:continue
            counts=waves[key]
            assert counts['two']['committed']==c['neural_rhs']
            for v in counts.values():
                assert v['semantic_exact'] and v['committed']+v['exact_rhs']==data['rhs'] and len(v['ms'])==6
                assert sum(map(sum,v['per_wave']))==v['committed']
                assert v['raw']==v['accepted']+v['rejected']+v['duplicate']
                assert v['reference_winner_bound']==budgets[name]['budgets'][str(v['waves'])]['reference_winners']
            assert counts['null-stop']['unclaimed_at_stop']>0
    print('Verified receipt provenance, bootstrap boundary, dispatch, wave budgets and trace-only composition ceilings.')


if __name__=='__main__':check()

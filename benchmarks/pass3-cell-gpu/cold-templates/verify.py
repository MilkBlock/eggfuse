"""Validate held-out action exposure, online attribution, native cache sizes and cold/publication denominators."""
import json
from pathlib import Path


def verify(folder=None):
    d=Path(folder) if folder else Path(__file__).resolve().parent
    def read(n):return json.loads((d/n).read_bytes())
    training=read('training.json');results=read('results.json');isolation=read('isolated.json')
    assert len(training)==6 and len(results)==24 and len(isolation)==24
    expected_programs={'affine-twins','clamped-ramp','segmented-prefix','window-laplacian'}
    for seed in (1703,1709):
        arms=[training[f'{k}/{seed}'] for k in ('id','graph','compose')]
        assert arms[1]['trainable_parameters']==arms[2]['trainable_parameters']
        for t in arms:
            assert t['train_size']==40 and t['seen']==[33,36,37,39] and t['cold']==[32,38] and t['held_family']==55
            assert set(t['families'])==expected_programs and t['updates']==480
            for size,j,delta in [(40,8,8),(48,9,1),(64,15,6)]:
                view=t['snapshots'][str(size)]
                assert (view['admitted_pairs'],view['new_pairs'],view['template_bytes'])==(j,delta,j*96)
                assert view['encoded_bytes']==j*96+72 and view['full_vs_incremental_cache_error']<1e-5
                assert 1<=view['distinct_cold_codes']<=view['cold_units'] and (t['kind']!='id' or view['distinct_cold_codes']==1)
        for case in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax'):
            for size in (40,48,64):
                comparison=results[f'{case}/{seed}/{size}']
                for k in ('id','graph','compose'):
                    r=comparison[k]
                    assert r['source_aligned'] and r['neural_roots']+r['neural_children']+r['exact']==r['rhs']
                    assert len(r['samples_ms'])==(8 if size==64 else 6)
                    assert r['whole_nonempty']<=r['nonempty']
                    score=r['native_scorer'];assert score['discrete_difference']==0 and score['max_latent_difference']<1e-5
                    assert len(score['resident_batch_ms'])==20 and score['root_tokens']==2*r['runs']
                    cohort=r['cohorts']
                    assert sum(v['children'] for group,v in cohort.items() if group!='all')==r['neural_children']
                    for group,v in cohort.items():
                        assert v['matched_reference']+v['alternative_origin']==v['children']
                        assert v['matched_reference']<=v['two_slot_bound_given_actual_roots']<=v['two_slot_pair_bound']<=v['reference_reachable_pairs']
                        assert v['whole_release_runs']<=v['release_runs']
                        diag=r['conditioned'][group];assert diag['exact']<=diag['covered']
                        assert diag['missing']==diag['miss_all_abstain']+diag['miss_different_effect']+diag['miss_same_effect_wrong_receiver']
                        assert v['reference_child_rhs']==comparison['id']['cohorts'][group]['reference_child_rhs']
                    if size==40:assert cohort['growth']['reference_child_rhs']==cohort['growth']['emitted']==0
                    if size==64:
                        assert r['autonomous']['first_run_difference']==1 and r['autonomous']['exact_rhs']==0
                        isolated=isolation[f'{case}/{seed}/{k}']
                        assert isolated['source_aligned'] and len(isolated['opened'])==6
                        assert isolated['roles']['child_rhs']==r['neural_children']
    print('Verified real Pass 3 zero-update growth, complete cold cohorts, resident costs and isolated inference.')


if __name__=='__main__':verify()

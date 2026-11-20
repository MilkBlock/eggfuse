"""Validate reported closures and provenance totals, plus required Pass 3 counterexamples."""
import json
from pathlib import Path


def check(folder):
    all_cases=json.loads((folder/'results.json').read_bytes())
    for case,rhs in [('sum-bits',7265),('dot-product',6704)]:
        for seed in (1703,1709):
            tests=all_cases[f'{case}/{seed}']
            clean={k:v for k,v in tests.items() if k.endswith('-intact')}
            assert len(clean)==6
            origins={a['neural_committed'] for a in clean.values()}
            assert len(origins)==1 and min(origins)>0
            assert all(a['neural_committed']+a['bucket_committed']+a['residual_committed']==rhs for a in tests.values())
            assert all(a['false_closures']==0 and a['verified_pages']==a['verified_extent_audits'] for a in tests.values())
            assert all(len(a['ms'])==6 and a['median_ms']>0 for a in clean.values())
            single=clean['unique-unique-intact'];many=clean['partial-range-intact']
            assert single['full_key_claims']>0 and single['largest_observed_bucket']==1 and single['unique_index_visits']>0
            assert many['multirow_bucket_claims']>0 and many['bucket_committed']>0 and many['partial_page_claims']>0
            assert many['distinct_checked_keys']>=many['distinct_whole_keys_closed']>0
            assert many['distinct_retained_rows']>0 and many['residual_seed_checks_skipped']>0
            assert clean['partial-unique-intact']['distinct_source_rows_closed']==0
            for p in ('partial','unique'):assert clean[f'{p}-positive-intact']['distinct_source_rows_closed']==0
            if seed==1703:
                assert tests['partial-range-omit']['rejected_missing']>0 and tests['partial-range-omit']['omitted_reference_winners']>0
                assert tests['partial-range-stale']['rejected_stale_after_union']>0
                assert tests['partial-range-duplicate']['repeated_accepted_claims']>0
                assert tests['partial-range-null']['residual_committed']==rhs
                for lane in ('unique-positive-intact','unique-unique-intact','partial-range-intact'):
                    events=clean[lane]['synchronized_intervals']
                    assert any(e['wave']==2 and e['us']>0 for e in events)
                    assert any(e['wave']!=2 and e['us']>0 for e in events)
    print('Verified both source schedules, unique and partial coverage, versions, neural and exact attribution.')


if __name__=='__main__':check(Path(__file__).resolve().parent)

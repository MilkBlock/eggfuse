"""Verify measured scope and separate issued certificate identities from source RHS credits."""
import json
from pathlib import Path


def check(root):
    load=lambda n:json.loads((root/n).read_text())
    matrix=load('results.json');repeat=load('confirmed.json')
    assert len(matrix)==8 and set(repeat)==set(matrix)
    for key,arms in matrix.items():
        macro=arms['macro'];raw=arms['raw'];leaf=arms['leaf']
        assert raw['active_certificates']==leaf['active_certificates']==macro['active_certificates']
        assert all(arms[a]['candidate_scores']==macro['candidate_scores'] for a in ('raw','leaf','bad-witness'))
        for name in ('raw','leaf','macro'):
            r=arms[name];proof=repeat[key][name]
            assert r['aligned'] and r['source_rhs']==r['neural_rhs']+r['exact_residual']
            assert r['root_winners']+r['child_winners']==r['neural_rhs']
            assert r['one_rhs']+r['zero_rhs']+r['two_rhs_from_one_certificate']==r['active_certificates']
            assert r['emission_slots']==2*r['runs'] and len(r['inference_ms'])==len(r['cli_ms'])==8
            assert proof['same_source_ordinals'] and proof['all_events_equal'] and proof['extensions']==r['child_winners']
            unaided=arms[name+'-only'];assert unaided['exact_residual']==0 and unaided['first_divergence']==1
        assert macro['child_winners']==macro['two_rhs_from_one_certificate']>0 and macro['neural_rhs']>leaf['neural_rhs']
        assert raw['child_winners']==leaf['child_winners']==0
        assert macro['independent_pytorch_rollout']['discrete_differences']==0 and macro['independent_pytorch_rollout']['max_latent_difference']<.002
    for case,arms in load('metal-control.json').items():
        assert all(v['source_aligned'] for v in arms.values())
        assert arms['macro']['child']>0 and arms['leaf']['child']==arms['raw']['child']==0
    print('Verified single-emission CPU/Rust granularity, later member ordinals, independent rollouts and Metal controls.')


if __name__=='__main__':check(Path(__file__).resolve().parent)

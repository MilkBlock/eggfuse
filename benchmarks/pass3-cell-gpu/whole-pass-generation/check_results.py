"""Recheck full-pass attribution and source-schedule claims from the committed experiment evidence."""
from pathlib import Path
import json


def main(root):
    data=json.loads((root/'results.json').read_text())
    counts=json.loads((root/'proof-counts.json').read_text())
    iso=json.loads((root/'isolated.json').read_text())
    events=json.loads((root/'event-results.json').read_text())
    assert len(data)==8 and set(data)==set(counts)==set(iso)
    for case,lanes in data.items():
        learned=lanes['learned']
        assert learned['actual_rhs']==learned['reference_rhs']==learned['static_roots']+learned['child_winners']+learned['exact_residual']
        assert learned['first_divergence'] is None and learned['static_roots']==2
        assert lanes['point']['child_winners']==learned['child_winners'] and lanes['wrong-parent']['child_winners']==lanes['none']['child_winners']==0
        assert lanes['all']['child_winners']>=learned['child_winners'] and lanes['all']['point_route_attempts']>=learned['point_route_attempts']
        assert lanes['no-residual']['first_divergence']==3 and lanes['no-residual']['exact_residual']==0
        assert all(len(lanes[n]['ms'])==6 for n in ('exact','learned','all','point'))
        proof=counts[case]['learned']
        assert proof['issued']==proof['unused']+proof['neural_winners']
        assert proof['neural_winners']==proof['globally_projected_winners']+proof['local_recheck_winners']+proof['suffix_lookup_winners']
        assert proof['globally_projected_winners']==learned['projection_rhs']
        assert iso[case]['assisted']['sha256']==iso[case]['no_residual']['sha256']
        assert iso[case]['assisted']['child_winners']==learned['child_winners']
        if case in events:
            e=events[case]
            assert e['dense']['winners']==e['events']['winners']==learned['child_winners']
            assert e['events']['visits']<e['dense']['visits'] and e['events']['attempts']==e['dense']['attempts']
            assert e['proof-only']['winners']==learned['projection_rhs']
            assert e['proof-only-no-residual']['first_divergence']==3 and len(e['generation_and_global_sweep']['ms'])==16
            assert all(len(e[arm]['ms'])==8 for arm in ('dense','events','proof-only','exact'))
    assert len(events)==4
    print('Verified whole-pass attribution, universal and suffix proof counts, isolated forest identity and event activation.')


if __name__=='__main__':main(Path(__file__).resolve().parent)

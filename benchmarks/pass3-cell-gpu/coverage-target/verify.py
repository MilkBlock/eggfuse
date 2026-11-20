from pathlib import Path
from itertools import combinations
import json
from addressability import minimum_witnesses


def check(root):
    source=json.loads((root/'source.json').read_bytes())
    measured=json.loads((root/'observed.json').read_bytes())
    for name,r in source.items():
        assert r['target']==(98*r['rhs']+99)//100
        assert sum(r['by_minimum_witnesses'].values())==r['rhs']==sum(t['committed'] for t in r['rules'])
        assert r['required_multi_at_98']==r['target']-r['bound_if_only_zero_and_one']>0
        for seed in (1703,1709):
            m=measured[f'{name}/{seed}'];assert m['source_rhs']==r['rhs'] and m['ordered_endpoints_equal']
            assert m['neural_rhs']==m['root_rhs']+m['child_rhs']
            assert m['missing_to_target']==r['target']-m['neural_rhs']
            assert m['new_physical_cells']==m['outside_rhs']+m['allocated_inside_rhs']>=m['cells_allocated_during_neural_rhs']
    # An inverse functional dependency must not accidentally make a true two-parent rule single-root.
    assert len(minimum_witnesses({'q':[[0,[0,2]],[1,[1,2]]]},set()))==2
    assert len(minimum_witnesses({'q':[[0,[0,1]],[1,[1,2]],['+',[2,-1,3]]]}, {'+'}))==1
    assert minimum_witnesses({'q':[[0,[-1,0]],[1,[0,1]]]},set())==()
    print('Verified per-workload 98% denominator, witness lower bounds, actual neural ordinals and allocation shares.')


if __name__=='__main__':check(Path(__file__).resolve().parent)

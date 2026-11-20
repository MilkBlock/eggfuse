"""Final acceptance on one source-aligned native execution per input, seed and predeclared policy."""
import json
from pathlib import Path


def check(folder):
    gpu=folder.parent
    def read(file):return json.loads(file.read_bytes())
    results=read(gpu/'joint-root-cells/results.json')
    ids=read(gpu/'joint-root-cells/physical-proof.json')
    endpoint=read(gpu/'joint-witness/results/bundles.json')
    required=read(folder/'source.json')
    assert len(results)==len(ids)==16 and len(endpoint)==8
    report={}
    for key,arms in results.items():
        case,seed,regime=key.split('/')
        v=arms['use'];n=required[case]['rhs']
        assert v['source_exact'] and v['rhs']==n
        assert 100*v['neural_rhs']>=98*n and 100*v['direct_distinct']>=98*v['fresh']
        assert v['root_consumed']==v['neural_rhs'] and v['direct_distinct']==v['direct_roots']+v['direct_children']
        assert all(arms[x]['direct_roots']==0 for x in ('withhold','shadow','wrong-port','wrong-template'))
        if regime=='certified':
            assert v['neural_rhs']==n and arms['use/no-fallback']['source_exact']
            b=endpoint[case+'/'+seed]['report']
            assert b['neural_rhs']==n and b['remaining_rhs']==0 and b['root_cells_allocated']==v['direct_roots']
        report[key]=dict(required_rhs=required[case]['target'],neural_rhs=v['neural_rhs'],source_rhs=n,
                         exact_other_rhs=n-v['neural_rhs'],verified_root_cells=v['direct_roots'],
                         verified_merge_cells=v['direct_children'],distinct_new_cells=v['direct_distinct'],all_new_cells=v['fresh'])
    return report


if __name__=='__main__':
    folder=Path(__file__).resolve().parent
    print(json.dumps(check(folder),indent=1))

"""Check a union of actual per-source-ordinal provider tickets from SINGLE joint trajectories."""
import json
from pathlib import Path


def check(folder):
    def read(name):return json.loads((folder/'results'/f'{name}.json').read_bytes())
    selective=read('selective');strict=read('no_residual');timing=read('timing')
    assert len(selective)==len(strict)==len(timing)==8
    for key,arms in strict.items():
        autonomous=arms['strict'];high=selective[key]['target']
        for v in (autonomous,high):
            assert v['aligned'] and all(v['checks'].values()) and v['valid_98'] and v['pass_without_zero_witness']
            assert v['neural_single']+v['neural_multi']==v['total_attributed']==v['source_rhs']-v['uncredited']
            assert v['single_work'][1]<v['single_work'][0] and v['multi_work']['exhausted']==0
            assert v['multi_work']['raw_tuples']>=v['multi_work']['validated']>=v['neural_multi']>0
            cell=v['instance_audit']
            assert cell['source_rule_template_matches']+cell['named_nested']==cell['joint_named_fresh']
            assert cell['merge_controls'][5]==cell['named_nested']>0
            assert cell['joint_cell_98'] and 100*cell['joint_named_fresh']>=98*cell['fresh_instances']
            assert cell['distinct_fresh_ids']==cell['fresh_instances'] and cell['joint_named_fresh']<=v['cells_in_neural_rhs']
        assert not high['multi_residual'] and high['single_residual']
        assert not autonomous['multi_residual'] and not autonomous['single_residual'] and autonomous['uncredited']==0
        assert all(len(x['ms'])==6 for x in timing[key].values())
        assert timing[key]['high']['learned_rhs']==high['total_attributed']
        assert timing[key]['certified']['learned_rhs']==autonomous['total_attributed']
    assert len(read('development'))==4 and all(v['strict']['aligned'] and v['strict']['uncredited']==0 for v in read('development').values())
    for key,v in read('negative').items():
        assert v['null-single']['neural_single']==v['null-multi']['neural_multi']==0
        assert not v['strict']['aligned'] and not v['none-only']['aligned']
    print('Verified joint 98% RHS and distinct explicitly named fresh Cell IDs, closures, controls and timed pairs.')


if __name__=='__main__':check(Path(__file__).resolve().parent)

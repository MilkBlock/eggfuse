"""Capture source-scored inputs and verify the work denominators in separate untimed inferences."""
from argparse import ArgumentParser
import json
from pathlib import Path
from runpy import run_path
HERE=Path(__file__).resolve().parent
driver=run_path(str(HERE/'study.py'))
wave=driver['wave'];source=driver['source']
if __name__=='__main__':
    p=ArgumentParser()
    for key in ('exp','native','heldout','out'):p.add_argument(key,type=Path)
    a=p.parse_args();a.seed=1703;a.cap=8192
    a.policy=json.loads((HERE.parent/'speculative-allocation-policy/policy.json').read_bytes())
    a.fraction=json.loads((HERE.parent/'wave-demand-policy/policy.json').read_bytes())['models']['fraction']
    a.out.mkdir(parents=True,exist_ok=False)
    held=json.loads(a.heldout.read_bytes());out={}
    for case,rows in held.items():
        prog,plan,req=source.common.config(a,case);base=wave['settings'](req,a)['packed'];out[case]={}
        with source.base.session(a.native,prog,plan) as infer:
            for arm,options in [('off',dict(enabled=False)),('group',dict(enabled=True,weights=json.loads((HERE/'policy.json').read_bytes())['weights'])),('all',dict(enabled=True))]:
                v=infer(dict(base,pair_actor=options));q=rows[arm];g=v['multi']['pair_actor']
                assert v['state_sha']==q['state_sha'] and g==q['stats']
                singles=v['single']['work'];mc=v['multi']['counts'];residual=q['external'][1]
                assert singles[1]==q['single_scores'] and mc['verified_parent_tuples']==q['verified_parent_tuples']
                # Diagnostic counts are events, not wall-clock units or equal-cost FLOPs.
                all_decisions=singles[0]+residual+g['score_calls']+q['all_child_decisions']
                all_verifications=singles[2]+mc['raw_tuples']
                out[case][arm]=dict(single_score_inputs=singles[0],single_above_floor=singles[1],single_exact_checks=singles[2],
                    group_signature_opportunities=g['score_calls'],group_size_eligible=g['score_calls']-g['small_or_large'],
                    new_learned_gate_evaluations=(g['score_calls']-g['small_or_large'] if arm=='group' else 0),
                    explicit_multi_residual=residual,all_child_decisions=q['all_child_decisions'],
                    all_decisions=all_decisions,visible_per_all_decisions=q['visible']/all_decisions,
                    exact_parent_checks=all_verifications,visible_per_exact_parent_check=q['visible']/all_verifications,
                    root_visits=mc['root_offers'],approximate_pair_or_stack_visits=mc['approximate_visits'],
                    receiver_table_decodes=g['receiver_decoded'],receiver_verified_group_lanes=g['receiver_postings'])
        (a.out/'work.json').write_text(json.dumps(out,indent=1)+'\n')

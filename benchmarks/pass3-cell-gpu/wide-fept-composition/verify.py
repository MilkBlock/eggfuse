"""Reconcile all wide transfers, ancestral ledgers, component denominators, bounds and faults."""
from hashlib import sha256
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
def read(f):return json.loads((HERE/f).read_bytes())

def verify():
    for f,h in read('manifest.json')['files'].items():assert sha256((HERE/f).read_bytes()).hexdigest()==h,f
    r=read('results.json');assert set(r)=={'3mm','deriche','sum-bits'}
    fixed=('rhs','commits','physical','root_ids','root_parents','nested_ids','children','state_sha','single_winners',
           'multi_winners','raw_parent_sha','root_commit_sha','visible_sha','retired_sha','recurrent','decisions','rule_call_sha','birth_sha','born','visible',
           'expanded_single','expanded_multi','child_candidates','selected_children','source_work')
    for case,v in r.items():
        assert set(v['arms'])=={'packed','singleton','wide','joint'} and set(v['faults'])=={'single','wide'}
        base=v['arms']['packed']
        for arm,q in v['arms'].items():
            assert all(q['checks'].values()) and all(q[k]==base[k] for k in fixed)
            f=q['family_counts'];c=q['class_counts'];d=q['denominators'];g=q['categories']
            assert d['forward']==sum(x['packets'] for x in g.values())
            assert d['bidirectional']==d['forward']+c['issued']
            assert d['paid_groups']==d['forward']+f['absent']+f['stale']
            assert d['paid_plus_return']==d['paid_groups']+c['issued']
            assert d['all_prototype_decisions']==q['single_dispatches']+c['issued']+q['single_residual_decisions']+g['multi_literal']['packets']+f['actions']+f['prototypes']+q['child_candidates']
            assert d['decisions_plus_return']==d['all_prototype_decisions']+c['issued']
            assert all(q['per_packet'][k]==q['visible']/n for k,n in d.items())
            assert sum(x['visible'] for x in g.values())==q['visible'] and sum(x['born'] for x in g.values())==q['born']
            assert c['internal_receipts']+g['single_literal']['packets']==q['expanded_single']
            assert f['private_rows']+g['multi_literal']['packets']==q['expanded_multi']
            assert sum(q['arity'].values())==sum(q['residual_query_width'].values())==g['multi_literal']['packets']
            assert f['candidate_bound']==f['receiver_pairs'] and f['matched_min_packets']<=f['actions']
            assert q['max_total_for_fept_two']==q['visible']//2 and q['budget_remaining_after_forward']==q['visible']//2-d['forward']
            assert q['wide_actions_affordable_at_fept_two']==q['visible']//2-(d['forward']-f['actions'])
            assert q['optimistic_matched_packets']==d['forward']-f['actions']+f['matched_min_packets']
            assert q['optimistic_matched_fept']==q['visible']/q['optimistic_matched_packets']
            assert q['bi_bytes']==sum(q['wire'].values())
            assert len(q['ms'])==len(q['wall_ms'])==4
        assert all(v['arms']['joint'][k]==v['arms']['wide'][k] for k in ('family_counts','arity'))
        for k in ('issued','internal_receipts','residual_receipts','feedback_bytes','masks'):
            assert v['arms']['joint']['class_counts'][k]==v['arms']['singleton']['class_counts'][k]
    print('Three source workloads, both actors, all charged packet conventions, exact residual arities and fault checks verified.')

if __name__=='__main__':verify()

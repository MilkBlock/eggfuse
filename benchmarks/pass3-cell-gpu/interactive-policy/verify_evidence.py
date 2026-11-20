"""Audit attribution, fixed-work controls and the interpretation of immediate i64 transaction benefits."""
import json
from pathlib import Path


def check(folder):
    source=json.loads((folder/'results.json').read_bytes())
    budgets=json.loads((folder/'matched.json').read_bytes())
    assert len(source['train'])==4 and set(source['learned'])=={'1703','1709'}
    for seed,policy in source['learned'].items():
        assert policy['trainable_parameters']==691
        for name,consumed in [('sum-bits',260),('dot-product',160),('gemm-bias-relu',527),('stable-argmax',260)]:
            for cohort in ('source','neural'):
                scope=policy['samples'][f'{name}/{cohort}']
                cpu=scope['devices']['cpu'];gpu=scope['devices']['mps']
                for arm in ('blind','guard','value','both-values','deferred','native-deferred','native-deferred-all'):
                    v=cpu[arm]
                    for metric in ('selected','true_distinct','unobserved','missed','complete_nonempty','matched_optional'):
                        assert v[metric]==gpu[arm][metric]
                    assert v['selected']==v['true_distinct']+v['unobserved']
                    assert v['distinct_consumers']==v['true_distinct']+v['missed']
                    assert v['future_rhs']==v['distinct_consumers']+v['source_ordinals_beyond_one_per_port_consumer']
                assert cpu['guard']['complete_nonempty']==cpu['deferred']['complete_nonempty']
                assert cpu['blind']['requests']==0 and cpu['guard']['requests']==scope['dynamic_b']
                assert cpu['both-values']['requests']==scope['dynamic_a']+scope['dynamic_b']
                assert cpu['native-deferred']['superseded_but_later_source_consumed']==0
                if cohort=='source':
                    assert cpu['blind']['consumed']==consumed
                    assert scope['information']['guard']['bits']>1
                else:
                    assert scope['dynamic_b']==0 and scope['dynamic_a']==scope['ports']
                    assert cpu['both-values']['vs_blind']['changed_output_ports']==0
                for mode in ('pooled','separate'):
                    row=budgets[f'{name}/{seed}/{cohort}/{mode}']
                    assert len({r['selected'] for r in row.values()})==1
                    delta=row['both-values']['complete_nonempty']-row['blind']['complete_nonempty']
                    assert delta==(2 if (name,seed,cohort,mode)==('sum-bits','1703','source','pooled') else 0)
    print('Verified source vs neural origin, both-device decisions, symbolic guards, and matched per-epoch budgets.')


if __name__=='__main__':check(Path(__file__).resolve().parent)

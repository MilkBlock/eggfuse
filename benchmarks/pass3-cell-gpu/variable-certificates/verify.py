"""Verify full Pass 3 provenance, port-width losses and the separate genuinely presealed raw-value arm."""
import json
from pathlib import Path

def verify(folder=None):
    root=Path(folder) if folder else Path(__file__).resolve().parent
    def read(n):return json.loads((root/n).read_text())
    results=read('results.json');direct=read('sealed-values.json');allocation=read('allocation.json');faults=read('adversarial.json')
    assert len(results)==len(direct)==8 and len(allocation)==32 and len(faults)==16
    for key,row in results.items():
        arms=row['arms'];b=arms['boundary'];complete=b['neural_children']
        assert b['payload']['extra_reference_slots']==b['payload']['typed_value_slots']==0
        assert b['exact']+complete+b['compiler_static_roots']==b['all_rhs']
        assert arms['fixed6']['neural_children']==arms['all']['neural_children']==complete
        for name in ('fixed4','fixed6','all','boundary'):
            a=arms[name];alloc=allocation[f'{key}/{name}'];assert a['source_aligned'] and len(a['samples_ms'])==8
            assert a['exact']+a['neural_children']+a['compiler_static_roots']==a['all_rhs']
            assert a['neural_children']+a['reference_overflow']==complete and a['autonomous']['exact']==0
            assert alloc['source_aligned'] and alloc['vec_capacity_payload_bytes']>=alloc['reserved_payload_bytes']
            assert sum(c['won'] for n,c in a['cohorts'].items() if n in ('cold','seen'))==a['neural_children']
        assert arms['wrong-reference']['neural_children']==arms['wrong-value']['neural_children']==0
        for kind in ('valid-wrong-copy','valid-wrong-ref'):
            t=faults[f'{key}/{kind}'];assert t['source_aligned'] and t['reference']==complete
            if kind=='valid-wrong-ref':assert t['won']+t['different_live_expression']==complete and t['undetected_wrong_reference']==0
        for cap in ('4','6'):
            v=direct[key]['arms'][cap];assert v['source_aligned'] and v['copy_slots']==0
            assert v['children']<=v['full_slots_in_vocab']<=v['eligible_width']<=complete
            assert v['correct_fields']<=v['type_vocabulary_fields']<=v['total_fields']
            assert v['header']==row['header_sha256'] and v['autonomous']['exact']==0 and len(v['samples'])==8
    print('Verified complete CPU/Rust source traces, value and port controls, width limits, and isolated raw-value predictions.')

if __name__=='__main__':verify()

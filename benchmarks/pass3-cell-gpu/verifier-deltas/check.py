"""Check the common source-typed forest and coverage boundary for every placement."""
import json
from pathlib import Path

def verify(folder=None):
    p=Path(folder) if folder else Path(__file__).resolve().parent;data=json.loads((p/'results.json').read_bytes())
    ready=json.loads((p/'ready-results.json').read_bytes())
    assert set(ready)==set(data)
    assert len(data)==8
    for key,d in data.items():
        a=d['assisted'];controls=d['no_residual'];reference=a['cpu-rust'];corrupt=a['corrupt']
        assert reference['neural_children']>0 and d['certificate_bytes']==24*d['slots']
        assert all(len(samples)==10 for samples in d['samples'].values())
        assert len(d['shared_sha'])==64 and d['universal_active']<=d['active']<=d['slots']
        for mode in ('cpu-rust','gpu-rust','delta','snapshot'):
            r=a[mode];assert r['source_aligned'] and r['child_ordinals']==reference['child_ordinals']
            assert r['static']+r['neural_children']+r['exact']==r['source_rhs']==r['actual_rhs']
            if mode in ('cpu-rust','gpu-rust'):assert all(t.get('sidecar') is None for t in d['samples'][mode])
        delta=a['delta']['sidecar'];snapshot=a['snapshot']['sidecar']
        assert delta['changed_port_records']==snapshot['changed_port_records']
        assert 0<delta['state_write_bytes']<snapshot['state_write_bytes'] and delta['launches']==snapshot['launches']>0
        assert delta['device_projected_replies_delivered']>=reference['neural_children'] and delta['reply_bytes']>0
        assert all(t['sidecar']['state_write_bytes']==delta['state_write_bytes'] for t in d['samples']['delta'])
        assert a['gpu-metal']['cross_typed_graph'] and a['gpu-metal']['cross_ordinals']
        assert corrupt['source_aligned'] and corrupt['neural_children']==0
        assert controls['delta']['child_ordinals']==controls['cpu-rust']['child_ordinals']
        assert controls['delta']['first_divergence'] is not None and controls['delta']['exact']==0
        assert controls['gpu-metal']['cross_ordinals'] and controls['gpu-metal']['exact_residual']==0
        pair=ready[key];before=pair['delta']['audit'];after=pair['ready']['audit']
        assert before['child_ordinals']==after['child_ordinals']==reference['child_ordinals']
        assert after['source_aligned'] and after['sidecar']['launches']==2<before['sidecar']['launches']
        assert after['sidecar']['source_scans']<before['sidecar']['source_scans']
        assert len(pair['ready']['samples'])==len(pair['delta']['samples'])==8
        assert all(t['sidecar']['launches']==2 for t in pair['ready']['samples'])

    print('Verified common GPU/CPU proposal words and universal child ordinals across native, mirrored Metal, and all-Metal execution.')

if __name__=='__main__':verify()

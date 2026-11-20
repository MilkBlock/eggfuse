"""Check placement boundaries, matching discrete outputs, actual RHS ordinals and timed sample counts."""
import json
from pathlib import Path


def verify(root):
    def read(name):return json.loads((root/name).read_text())
    full,compiled,recurrent,cli=map(read,['placement.json','compiled.json','recurrent.json','fresh-cli.json'])
    assert set(full)==set(compiled)==set(recurrent)==set(cli) and len(full)==4
    for key,arms in full.items():
        for arm,result in arms.items():
            assert len(result['ms'])==10 and len(result['paired_ms_vs_mps'])==10
            assert result['neural_rhs']==arms['mps']['neural_rhs'] and result['changed_winner_ordinals']==0
            if arm=='resident-replay':continue
            assert result['token_differences']==0 and result['params']==12829 and result['static_roots']==2
            assert result['cpu_to_gpu_token_bytes']==(20*result['candidates'] if arm.startswith('cpu') else 0)
        for arm,result in compiled[key].items():
            assert result['token_differences']==result['changed_winner_ordinals']==0 and len(result['ms'])==6
            assert result['neural_rhs']==arms['mps']['neural_rhs']
        for arm,result in recurrent[key].items():
            assert result['changed_rows']==result['changed_root_ordinals']==result['changed_child_records']==0
            assert result['max_latent_difference']<.002 and len(result['ms'])==8
            assert result['exact']+result['roots']+result['children']==result['rhs']==arms['mps']['source_rhs']
            assert result['logical_bytes_read']==(0 if arm=='metal' else 8192*(result['runs']+1))
        assert all(v['semantic_exact'] and len(v['ms'])==4 for v in cli[key].values())
    print('Verified whole-pass and recurrent CPU/MPS/Metal placement, handoff sizes and fresh-process checks.')


if __name__=='__main__':verify(Path(__file__).resolve().parent)

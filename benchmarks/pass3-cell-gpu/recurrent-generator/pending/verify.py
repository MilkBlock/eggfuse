"""Consistency checks for learned compound generation, frozen replay, masks and origin accounting."""
from pathlib import Path
import json


def check():
    root=Path(__file__).resolve().parent
    def read(name):return json.loads((root/name).read_text())
    results=read('results.json'); replay=read('replays.json'); training=read('root-targets.json')
    negatives=read('rejected-parent.json')
    assert len(results)==8 and len(replay)==16 and len(negatives)>=4
    for key,arms in results.items():
        case,seed=key.split('/')
        isolated=read(f'isolated-{seed}.json')[case]
        assert isolated['neural_only']['actual_rhs']==0 and isolated['neural_only']['first_schedule_or_count_difference']==1
        for mode in ('batch','wave'):
            run=arms[mode]; frozen=replay[f'{key}/{mode}']; independent=frozen['actual']
            assert run['aligned'] and len(run['ms'])==6 and run['roots']+run['children']+run['exact']==run['rhs']
            assert independent['neural_children']==run['children']==independent['same_reference_winner_ticket']>0
            assert independent['pytorch']['discrete_differences']==0 and independent['pytorch']['max_latent_difference']<.002
            assert all(v['source_aligned'] and v['verified_child_ordinals']==run['children'] for v in frozen['replays'].values())
            assert frozen['replays']['wave']['claims_sha256']==frozen['replays']['batch']['claims_sha256']
            assert arms[mode+'-only']['exact']==0 and arms[mode+'-only']['first_divergence']==1
        assert arms['batch-masked']['children']==arms['wave-null']['children']==0
        assert training[key]['continuation']['children']==arms['batch']['children']
        assert training[key]['continuation']['children']>training[key]['leaf']['children']
    print('Checked learned compound selections, distinct child ordinals, isolated runs and frozen replays.')


if __name__=='__main__':check()

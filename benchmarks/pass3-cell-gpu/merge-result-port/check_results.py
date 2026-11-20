import json
from pathlib import Path


def check(root):
    data=json.loads((root/'versioned-results.json').read_bytes());timing=json.loads((root/'timing-results.json').read_bytes())
    assert len(data)==8 and set(data)==set(timing)
    for key,v in data.items():
        a=v['arms'];h=a['high-repeat']
        assert a['swap']['actual_children']==a['withheld']['actual_children']==0
        assert a['withheld']['first_divergence'] is not None and h['first_divergence'] is None
        assert h['actual_children']==h['removed_exact_duplicates'] and h['after_revalidation']>0 and h['second_or_later']>0
        assert h['actual_children']>=a['one-shot']['actual_children']>0
        assert a['repeat-pinned']['after_revalidation']==0
        assert all(len(t['ms'])==8 for t in timing[key].values())
    print('Validated genuine neural-parent merge-result continuations on 8 current Pass 3 evaluations.')


if __name__=='__main__':check(Path(__file__).resolve().parent)

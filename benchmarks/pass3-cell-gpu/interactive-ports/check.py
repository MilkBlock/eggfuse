"""Check the interactive protocol, compare the paired controls and summarize native work."""
import json
from pathlib import Path
import sys


def check(data):
    source = ('state_sha','rhs','writes','graph_events','schedule')
    arms = {}
    for example in data['eval']:
        has_pair = example['kind'] != 'absent'
        for mode,result in example['arms'].items():
            totals=arms.setdefault(mode,dict(source_equal=0,strict_equal=0))
            for key in ('paid','receiver_reads','queries','pointer_scores','encodings','internal','rejected','transfers'):
                totals[key]=totals.get(key,0)+result[key]
            ok=all(result['checks'][k] for k in source)
            totals['source_equal']+=int(ok)
            totals['strict_equal']+=int(all(result['checks'].values()))
            if mode in ('leaf','learned','full') and (not ok or result['rejected']):
                raise ValueError((example['seed'],mode,result))
            if mode=='learned' and has_pair and result['uses']!=[[1,True]]:
                raise ValueError('successor did not consume the signed owner export')
            if mode in ('bad-owner','stale') and has_pair and (ok or result['rejected']==0):
                raise ValueError('receiver filled a missing independent parent')
            if mode=='old-owner' and example['kind']=='reuse' and (ok or result['rejected']==0):
                raise ValueError('retired export was accepted')
    if arms['learned']['paid']>=arms['leaf']['paid']:
        raise ValueError('no independent proposals removed')
    if arms['unconditioned']['source_equal']>=arms['learned']['source_equal']:
        raise ValueError('no sensitivity to the chosen first parent')
    return dict(held_out=len(data['eval']),train_cases=len(data['train']),
                skip_pairs=len(data['skip_pairs']),arms=arms)


if __name__=='__main__':
    print(json.dumps(check(json.loads(Path(sys.argv[1]).read_bytes())),indent=2))

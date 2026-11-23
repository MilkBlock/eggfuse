"""Archive each full Run's native recall alongside exclusive and synthetic controls."""
import argparse
from pathlib import Path
import json
import shutil

from mixed_results import exclusive, read


def report(folder, output):
    evidence = dict(training=read(folder/'training.json'), native=read(folder/'native.json'),recall={})
    training = evidence['training']
    visits = training['visits']
    if (visits['busy'] != visits['empty'] or visits['stop'] != visits['busy'] + visits['empty']
            or visits['teacher_issues'] != training['epochs'] * training['source']['teacher_commits']):
        raise ValueError('incomplete or unbalanced Run training ledger')
    held = read(folder/'held.json')
    evidence['splits']={k:dict(shadow=v['shadow'],exclusive=exclusive(v['exclusive']['cases']))
                        for k,v in held['splits'].items()}
    output.mkdir(parents=True,exist_ok=True)
    for name in evidence['native']['cases']:
        src = folder/f'recall-{name}'
        r = read(src/'summary.json')
        if (r['weights_sha256']!=evidence['native']['weights_sha256']
                or r['receiver_sha256']!=held['build_sha256'] or r['teacher_control']):
            raise ValueError('unpaired reports')
        case = r['cases'][name]
        if case['teacher_commits'] != evidence['native']['cases'][name]['exclusive']['counts']['reference_commits']:
            raise ValueError('different teacher population')
        capped = read(folder/f'capped-{name}'/'summary.json')
        if (capped['weights_sha256'] != r['weights_sha256'] or capped['receiver_sha256'] != r['receiver_sha256']
                or capped['wave_limit'] != 1 or r['wave_limit'] <= 1):
            raise ValueError('different one-wave control')
        evidence.setdefault('same_weights_first_wave',{})[name] = capped['cases'][name]
        evidence['recall'][name] = case
        shutil.copyfile(src/f'{name}.csv',output/f'{name}.csv')
    (output/'summary.json').write_text(json.dumps(evidence,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder',type=Path)
    p.add_argument('output',type=Path)
    a=p.parse_args()
    report(a.folder,a.output)

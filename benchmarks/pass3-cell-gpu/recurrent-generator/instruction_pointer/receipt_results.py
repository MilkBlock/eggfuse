"""Check equivalence controls and archive both sides of the receipt experiment."""
import argparse
import csv
from pathlib import Path
import json
import shutil

from mixed_results import exclusive, read


def rows(path):
    with path.open() as f:
        return list(csv.DictReader(f))


def report(folder, previous, output):
    result = dict(training=read(folder/'training.json'),native=read(folder/'exclusive.json'),
                  transport_parity=read(folder/'native-parity.json'),teacher_parity=read(folder/'teacher-parity.json'),
                  sum_bits_semantic_status=read(folder/'sum-semantic.json')['status'],recall={},controls={})
    if result['sum_bits_semantic_status']!='pass':
        raise ValueError('incomplete sum-bits semantic acceptance')
    baseline = read(previous/'summary.json')
    held = read(folder/'held.json')
    result['splits'] = {k:dict(exclusive=exclusive(v['exclusive']['cases']),
                               shadow_without_receipts=v['shadow']) for k,v in held['splits'].items()}
    output.mkdir(parents=True,exist_ok=True)
    for n,case in result['native']['cases'].items():
        live = folder/f'live-{n}'
        raw = read(live/'summary.json')
        if raw['masked'] or not raw['live_receipts'] or raw['weights_sha256']!=result['native']['weights_sha256']:
            raise ValueError('expected interactive checkpoint')
        if raw['receiver_sha256']!=held['build_sha256']:
            raise ValueError('mismatched receiver')
        oracle_dir=folder/'oracle-complete-history'
        oracle=read(oracle_dir/'summary.json')
        if not oracle['oracle_rules'] or oracle['mode']!='assist' or oracle['weights_sha256']!=raw['weights_sha256']:
            raise ValueError('expected frozen parent ceiling')
        oracle_case=oracle['cases'][n]
        result['controls'].setdefault('oracle_rules',{})[n]=oracle_case
        csv_name = n+'.csv'
        before = rows(previous/csv_name)
        after = rows(live/csv_name)
        maximum=rows(oracle_dir/csv_name)
        if any(b['run']!=a['run'] or int(a['recovered'])>int(b['recovered'])
               for a,b in zip(after,maximum,strict=True)):
            raise ValueError('policy exceeded the measured fixed-parent ceiling')
        if [(r['run'],r['teacher_commits']) for r in before]!=[(r['run'],r['teacher_commits']) for r in after]:
            raise ValueError('different teacher schedule')
        result['recall'][n] = raw['cases'][n]
        if sum(int(r['recovered']) for r in after)!=raw['cases'][n]['recovered']:
            raise ValueError('missing recovered commits')
        shutil.copyfile(live/csv_name,output/csv_name)
    masked = read(folder/'masked-fact'/'summary.json')
    if (not masked['masked'] or masked['weights_sha256']!=result['native']['weights_sha256']
            or rows(folder/'masked-fact/fact.csv')!=rows(previous/'fact.csv')):
        raise ValueError('receipt-blind continuation differs from frozen policy')
    result['controls']['masked_fact'] = masked
    frozen = read(folder/'frozen'/'summary.json')
    for n,c in frozen['cases'].items():
        b = baseline['same_weights_first_wave'][n]
        for k,v in b.items():
            if k!='live_transport' and c[k]!=v:
                raise ValueError(f'streamed frozen first wave differs: {n} {k}')
    result['controls']['frozen_first_wave'] = frozen
    (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('folder','previous','output'):
        p.add_argument(name,type=Path)
    a=p.parse_args()
    report(a.folder,a.previous,a.output)

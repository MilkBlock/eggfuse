import hashlib,json
from pathlib import Path
from runpy import run_path
from statistics import median
HERE=Path(__file__).resolve().parent
study=run_path(str(HERE/'study.py'))
m=json.loads((HERE/'manifest.json').read_bytes());policy=json.loads((HERE/'policy.json').read_bytes())
for k,h in m['sources'].items():assert hashlib.sha256((HERE.parent/k).read_bytes()).hexdigest()==h,k
assert hashlib.sha256((HERE/'policy.json').read_bytes()).hexdigest()==m['policy']
assert set(policy['chosen'])=={k for k,x in policy['training'].items()if study['training'].fitted(x)>=policy['threshold']}
previous=json.loads((HERE.parent/'integral-filter-joint/results.json').read_bytes())
for case,r in json.loads((HERE/'results.json').read_bytes()).items():
    study['check'](case,r)
    baseline=previous[case]['filter_mixed'];q=r['off']
    assert (baseline['emitted'],baseline['packets'],baseline['owned_births'],baseline['visible'],baseline['state_sha'])==(q['emitted'],q['packets'],q['new'],q['visible'],q['state_sha'])
    for n in ('off','learned','all'):
        x=r[n];assert len(x['ms'])==4 and x['median_ms']==median(x['ms'])
    print(case,r['off']['visible_per_packet'],r['learned']['visible_per_packet'],r['learned']['actual_packet_change'])

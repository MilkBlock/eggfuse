import hashlib
import importlib.util
import json
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('joint',HERE/'study.py');study=importlib.util.module_from_spec(sp);sp.loader.exec_module(study)
manifest=json.loads((HERE/'manifest.json').read_bytes())
for name,sha in manifest['sources'].items():assert hashlib.sha256((HERE.parent/name).read_bytes()).hexdigest()==sha,name
cost=json.loads((HERE/'cost.json').read_bytes())
for case,rows in json.loads((HERE/'results.json').read_bytes()).items():
    study.check(rows)
    for name in study.MODES:
        q=rows[name];c=cost[case][name]
        assert q['state_sha']==c['state_sha'] and q['emitted']==c['emitted'] and q['regular_verifications']==c['regular_verifications']
        assert len(q['ms'])==len(q['wall_ms'])==4 and q['median_ms']==median(q['ms']) and q['median_wall_ms']==median(q['wall_ms'])
        assert q['packets']==sum(q['emitted'])+q['selected_child'] and q['visible_per_packet']==q['visible']/q['packets']
        assert q['new_per_packet']==q['owned_births']/q['packets']
    print(case,[(k,rows[k]['emitted'][0],rows[k]['median_ms'])for k in study.MODES])

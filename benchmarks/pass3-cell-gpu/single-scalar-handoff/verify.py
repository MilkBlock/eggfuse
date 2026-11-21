import importlib.util
import json
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('handoff_study',HERE/'study.py')
study=importlib.util.module_from_spec(sp)
sp.loader.exec_module(study)
for case,rows in json.loads((HERE/'results.json').read_bytes()).items():
    study.check(case,rows)
    for name in ('vanilla','off','filter','ports'):
        q=rows[name]
        assert len(q['ms'])==len(q['wall_ms'])==6 and median(q['ms'])==q['median_ms']
    q=rows['ports']
    print(case,'matching positive references',q['point_transfers'],'filtered vs handoff',rows['filter']['median_ms'],q['median_ms'])

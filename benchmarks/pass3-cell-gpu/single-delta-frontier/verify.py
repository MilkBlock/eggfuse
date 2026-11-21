import importlib.util
import json
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('frontier_study',HERE/'study.py')
study=importlib.util.module_from_spec(sp);sp.loader.exec_module(study)
for case,rows in json.loads((HERE/'results.json').read_bytes()).items():
    study.check(case,rows)
    for q in rows.values():assert len(q['ms'])==len(q['wall_ms'])==6 and median(q['ms'])==q['median_ms']
    assert len(rows['delta']['diagnostic_ms'])==3
    print(case,rows['delta']['delta']['point_lookups'],rows['filter']['median_ms'],rows['delta']['median_ms'])

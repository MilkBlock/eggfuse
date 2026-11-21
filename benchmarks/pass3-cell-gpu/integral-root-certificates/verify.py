import importlib.util
import json
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('integral_study',HERE/'study.py')
study=importlib.util.module_from_spec(sp);sp.loader.exec_module(study)
for case,rows in json.loads((HERE/'results.json').read_bytes()).items():
    study.check(case,rows)
    for n in ('vanilla','off','verify','apply'):
        q=rows[n];assert len(q['ms'])==len(q['wall_ms'])==4 and median(q['ms'])==q['median_ms']
    q=rows['apply']['integral'];c=q['counts'];print(case,c['external_seeds'],c['credited'],c['root_outputs'],c['child_outputs'],q['fanout'])

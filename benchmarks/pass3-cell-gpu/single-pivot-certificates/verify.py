"""Validate saved physical/source equivalence and complete omission audit."""
import importlib.util
import json
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('scalar_study',HERE/'study.py')
study=importlib.util.module_from_spec(sp)
sp.loader.exec_module(study)

def verify(path=HERE/'results.json'):
    report=json.loads(path.read_bytes())
    for case,rows in report.items():
        assert set(rows)=={'vanilla','off','on'}
        off,on=rows['off'],rows['on']
        study.check(case,on,off)
        assert off['audited']==off['omitted']==0
        assert all(q['checks'][k] for q in (off,on) for k in ('rhs','writes','resumes','unions','schedule','runs','state_sha'))
        for r in on['module'].values():assert r['audited']==r['missing']+r['stale']<=r['examined']
        for q in rows.values():assert len(q['ms'])==6 and median(q['ms'])==q['median_ms']
        print(case,on['omitted'],round(off['median_ms'],2),round(on['median_ms'],2))

if __name__=='__main__':verify()

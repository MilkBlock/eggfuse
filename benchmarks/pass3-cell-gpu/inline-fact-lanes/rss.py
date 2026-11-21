"""Peak RSS of one complete fresh process including load, inference, export and teardown."""
import argparse
import json
from pathlib import Path
import re
from statistics import median
import subprocess
import importlib.util

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('lane_study',HERE/'study.py')
study=importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)

def sample(binary,program,plans,request):
    child=subprocess.run(['/usr/bin/time','-l',binary,program,plans],input=json.dumps(request)+'\n',
                         capture_output=True,text=True,check=True)
    rss=re.search(r'^\s*(\d+)\s+maximum resident set size',child.stderr,re.MULTILINE)
    if rss is None:raise ValueError('macOS /usr/bin/time -l RSS is missing')
    return json.loads(child.stdout),int(rss[1])

def run(a):
    a.out.mkdir(parents=True,exist_ok=True)
    results={}
    for case in a.cases:
        program,plans,req=study.source.config(a,case)
        config=study.configurations(req)
        with study.source.base.session(a.exp/'compact-vanilla-20261121/vanilla',program) as ref:gold=ref({})
        names=list(config)
        rows={k:dict(peak_rss_bytes=[],source_ms=[]) for k in names}
        for lap in range(a.repeats):
            offset=lap%len(names);seq=names[offset:]+names[:offset]
            for name in seq if lap%2 else reversed(seq):
                exe,request=config[name]
                v,rss=sample(a.build/exe,program,plans,dict(request,audit=False))
                assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs']
                assert v['multi']['total_rhs']==gold['rhs_count']
                rows[name]['peak_rss_bytes'].append(rss);rows[name]['source_ms'].append(v['ms'])
        for row in rows.values():row['median_peak_rss_bytes']=median(row['peak_rss_bytes'])
        results[case]=rows
        (a.out/'rss.json').write_text(json.dumps(results,indent=1)+'\n')
        print(case,[(k,v['median_peak_rss_bytes']) for k,v in rows.items()],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','build','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['conjugate-gradient','3mm'])
    p.add_argument('--repeats',type=int,default=3)
    run(p.parse_args())

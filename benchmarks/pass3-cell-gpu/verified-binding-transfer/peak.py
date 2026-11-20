"""Measure whole native process high-water RSS, including setup and final export."""
import argparse
import json
import re
import subprocess
from pathlib import Path
from statistics import median
from runpy import run_path
driver=run_path(str(Path(__file__).with_name('study.py')))
base,choices=driver['base'],driver['choices']

def run(a, compare_arms=('off','run-tickets','all'), configure=choices):
    a.out.mkdir(parents=True,exist_ok=False)
    measured=json.loads(a.timing.read_bytes())
    results={}
    for case,g in measured.items():
        p,plan,req=base.common.config(a,case)
        arms=configure(req,a)
        samples={name:[] for name in compare_arms}
        for i in range(4):
            names=list(samples)
            names=names[i%len(names):]+names[:i%len(names)]
            for name in names:
                cmd=['/usr/bin/time','-l',a.native,p,plan]
                done=subprocess.run(cmd,input=json.dumps(dict(arms[name],audit=False))+'\n',text=True,capture_output=True,check=True)
                report=json.loads(done.stdout)
                assert report['state_sha']==g['off']['state_sha'] and report['runs']==g['vanilla']['runs']
                assert report['multi']['total_rhs']==g['vanilla']['rhs']
                assert report['root_recipe']['allocated']==g[name]['root_allocated']
                rss=int(re.search(r'^\s*(\d+)\s+maximum resident set size',done.stderr,re.M)[1])
                if i: samples[name].append(rss)
        results[case]={n:{'bytes':v,'median':median(v)} for n,v in samples.items()}
        (a.out/'rss.json').write_text(json.dumps(results,indent=1)+'\n')
        print(case,results[case],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','timing','out'):p.add_argument(k,type=Path)
    run(p.parse_args())

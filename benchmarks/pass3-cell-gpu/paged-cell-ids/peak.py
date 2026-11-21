"""Fresh OS process memory high-water measurements with the same source and physical checks."""
import argparse,importlib.util,json,re,subprocess
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('paired_layout',HERE/'study.py')
entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)

def run(a):
    a.out.mkdir(parents=True,exist_ok=False);data={}
    labels=json.loads(a.timing.read_bytes())
    for case in a.cases:
        p,plans,req=entry.source.config(a,case)
        req.update(header_mode=3,derived_ports={'mode':1,'cache':True},lazy_equations=4)
        modes=entry.MODES;samples={k:[] for k in modes}
        for i in range(4):
            for m in modes[i:]+modes[:i]:
                v=subprocess.run(['/usr/bin/time','-l',a.build/m,p,plans],input=json.dumps(req)+'\n',text=True,capture_output=True,check=True)
                report=json.loads(v.stdout);want=labels[case][m]
                assert report['state_sha']==want['state_sha'] and report['root_recipe']['allocated']==want['root_allocated'] and report['multi']['total_rhs']==want['rhs']
                if i:samples[m].append(int(re.search(r'^\s*(\d+)\s+maximum resident set size',v.stderr,re.M)[1]))
        data[case]={m:dict(samples=v,median=median(v)) for m,v in samples.items()}
        (a.out/'rss.json').write_text(json.dumps(data,indent=1)+'\n')
        print(case,[(k,round(v['median']/2**20,1)) for k,v in data[case].items()],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','build','timing','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['conjugate-gradient','3mm'])
    a=p.parse_args();a.seed=1703;run(a)

"""Sample the unchanged signed complete-generation arm on the two frozen source programs."""
import argparse
import json
import subprocess
from pathlib import Path
from time import perf_counter
import importlib.util
HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('integrated_sample',HERE.parent/'integrated-cpu-policy/measure.py')
base=importlib.util.module_from_spec(sp);sp.loader.exec_module(base)

def run(a):
    a.out.mkdir(parents=True,exist_ok=False)
    admission=base.read(HERE.parent/'single-signature-frontier/admission.json')['parameters']
    for case in ('3mm','deriche'):
        b=a.exp/'extra-pass3-transfer-v1'/f'{case}-1703';p=b/'program.json';q=base.read(b/'request.json');w=a.exp/'baked-port-packed-study-v1'
        for k in ('single_config','merge_config'):q[k]=str(b/q[k])
        root=a.out/f'{case}-root.json';root.write_text(json.dumps(dict(control='use',encoding='checked_slots',forbid_fallback=True)))
        q.update(root_config=str(root),multi_weights=str(w/'sum-bits-1703-tied.json'),baked_codes=str(w/'sum-bits-1703-tied.bin'),
            packed_lookup=True,baked_row_index=False,radius=0,multi_generation='complete',multi_mode='rowdeltapairguardstackseal2xlearned',
            early_guards='constants',rows=dict(action=4,max_rows=1,workers=1,batch=True,verify=2,prefilter=2))
        q=base.query(q,'all',admission);q.update(forward=dict(columns=2,budget=4<<20,existence=True,freshness=True,min_candidates=8),
            atom_constraints=2,tiered_ports=dict(primary=True,columns=True,evidence_views=1,bytes=1<<20))
        command=json.dumps(q)+'\n'
        with subprocess.Popen([a.native,p,b/'plans.json'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True) as proc:
            def call():
                proc.stdin.write(command);proc.stdin.flush();v=json.loads(proc.stdout.readline())
                return dict(state=v['state_sha'],runs=v['runs'],ms=v['ms'])
            warm=call();rows=[];dest=a.out/f'{case}.sample'
            with subprocess.Popen(['/usr/bin/sample',str(proc.pid),'10','1','-file',dest],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL) as profiler:
                while profiler.poll() is None:
                    r=call();assert (r['state'],r['runs'])==(warm['state'],warm['runs']);rows.append(r)
                assert profiler.returncode==0
            proc.stdin.close()
            (a.out/f'{case}-timing.json').write_text(json.dumps(rows,indent=1)+'\n')
            print(case,len(rows),warm,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('native','exp','out'):p.add_argument(k,type=Path)
    run(p.parse_args())

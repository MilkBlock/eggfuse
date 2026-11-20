"""Resident full-source timing with binary recipe issuance, validation and its native allocation paths charged."""
import argparse,json,subprocess
from pathlib import Path
from statistics import median
from time import perf_counter_ns
from study import joint,read


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('binary','ref','corpus','high','multi','merge','source','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False);results={}
    matrix=read(a.source/'results.json')
    for key,trial in matrix.items():
        case,seed,regime=key.split('/');program=a.ref/case/'program.json' if case in ('sum-bits','dot-product') else a.corpus/case/'program.json'
        single=a.high/f'{case}-{seed}-target.json' if regime=='high' else a.source/f'{case}-{seed}-certified.json'
        req=dict(single_config=str(single),multi_weights=str(a.multi/seed/'model.json'),multi_mode='stackseal3xlearned',multi_residual=False,
                 audit=False,cap=1000000,radius=2,merge_config=str(a.merge/f'{case}-{seed}-learned.json'))
        proc=subprocess.Popen([a.binary,program,a.high/f'{case}-plans.json'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        order=['prior','use'];report={k:dict(inference_ms=[],request_ms=[]) for k in order};state=None
        try:
            for i in range(10):
                for arm in order if i%2==0 else order[::-1]:
                    command=dict(req)
                    if arm=='use':command['root_config']=str(a.source/f'{case}-{seed}-{regime}-use.json')
                    start=perf_counter_ns();r=joint.rpc(proc,command);wall=(perf_counter_ns()-start)/1e6
                    assert 'source_error' not in r
                    if state is None:state=r['state_sha']
                    assert state==r['state_sha'] and r['merge_child']['counts'][5]==trial['use']['direct_children']
                    if arm=='use':
                        q=r['root_recipe'];assert q['allocated']==trial['use']['direct_roots'] and q['applied']==trial['use']['root_consumed']
                    if i>=2:report[arm]['inference_ms'].append(r['ms']);report[arm]['request_ms'].append(wall)
            for v in report.values():v.update(median_ms=median(v['inference_ms']),median_request_ms=median(v['request_ms']))
            results[key]=report;(a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
            print(key,[round(v['median_ms'],2) for v in report.values()],flush=True)
        finally:
            proc.stdin.close();proc.wait()
            if proc.returncode:raise RuntimeError(proc.stderr.read().decode()[-2048:])

"""Time the combined source execution, with real merge allocation under frozen gates and matched controls."""
import argparse,json,subprocess
from pathlib import Path
from statistics import median
from time import perf_counter_ns
from evaluate import joint,read


def study(a):
    a.out.mkdir(parents=True,exist_ok=False);summary={}
    measured=read(a.study/'results.json')
    for key,arms in measured.items():
        case,seed=key.split('/');program=a.ref/case/'program.json' if case in ('sum-bits','dot-product') else a.corpus/case/'program.json'
        path=a.policies/f'{case}-plans.json';proc=subprocess.Popen([a.binary,program,path],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        base=dict(single_config=str(a.policies/f'{case}-{seed}-target.json'),multi_weights=str(a.multi/seed/'model.json'),multi_mode='seal3xlearned',
                  multi_residual=False,radius=2,cap=1000000,audit=False)
        order=['ordinary','null','shadow','learned'];results={k:dict(inference_ms=[],rpc_ms=[]) for k in order};truth=None
        try:
            for t in range(8):
                seq=order[t%4:]+order[:t%4]
                for arm in seq if t<4 else seq[::-1]:
                    req=dict(base)
                    if arm!='ordinary':req['merge_config']=str(a.study/f'{case}-{seed}-{arm}.json')
                    start=perf_counter_ns();r=joint.rpc(proc,req);rpc=(perf_counter_ns()-start)/1e6
                    assert 'source_error' not in r
                    if truth is None:truth=r['state_sha']
                    assert truth==r['state_sha']
                    if arm!='ordinary':
                        assert r['merge_child']['counts']==arms[arm]['counts'] and r['merge_child']['score_trajectory']==arms[arm]['raw_gate_hash']
                    results[arm]['inference_ms'].append(r['ms']);results[arm]['rpc_ms'].append(rpc)
            for k,v in results.items():
                v['median_inference_ms']=median(v['inference_ms']);v['median_rpc_ms']=median(v['rpc_ms'])
            summary[key]=results;(a.out/'results.json').write_text(json.dumps(summary,indent=1)+'\n')
            print(key,[(k,round(v['median_inference_ms'],2)) for k,v in results.items()],flush=True)
        finally:
            proc.stdin.close();proc.wait()
            if proc.returncode:raise RuntimeError(proc.stderr.read().decode()[-2048:])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('binary','ref','corpus','policies','multi','study','out'):p.add_argument(k,type=Path)
    study(p.parse_args())

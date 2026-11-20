"""Match cold CLI boundaries; rotate isolated processes and validate every persisted graph."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from statistics import median
import subprocess
import sys
import tempfile
from time import perf_counter_ns

HERE=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def run(root,reference,weights,cpu,output):
    report={}
    for case in ('sum-bits','dot-product'):
        variants=('cpu','baseline','shard','prefix')
        expected={v:sha(root/(f'oracle-{case}' if v=='cpu' else f'export-{case}')/'state.json') for v in variants}
        oracle=json.loads((root/f'oracle-{case}/report.json').read_text())['steps']
        for folder in (f'study-{case}-0', f'study-{case}-2', f'upper-{case}'):
            if json.loads((reference/folder/'check.json').read_text())['acceptance']!='pass':
                raise ValueError('require exact ordered audit first')
        samples={v:[] for v in variants}
        for j in range(-1,8):
            order=variants[j%4:]+variants[:j%4]
            if j>=4:order=order[::-1]
            for lane in order:
                with tempfile.TemporaryDirectory(dir=reference) as tmp:
                    dest=Path(tmp)/'export'
                    cmd=([cpu,'--program',root/case/'program.json','--output',dest] if lane=='cpu' else
                         [sys.executable,HERE/'run.py',root/f'release-input-{case}/device.json',weights,dest,
                          '--port-weights',root/'ports-1703.pt','--freshness',str({'baseline':0,'shard':2,'prefix':4}[lane]),'--export-only'])
                    start=perf_counter_ns()
                    subprocess.run(list(map(str,cmd)),env=dict(os.environ,PYTORCH_ENABLE_MPS_FALLBACK='0'),check=True,stdout=subprocess.DEVNULL)
                    wall=(perf_counter_ns()-start)/1e6
                    if sha(dest/'state.json')!=expected[lane]:raise ValueError((case,lane,'export digest mismatch'))
                    if lane=='cpu':
                        r=json.loads((dest/'report.json').read_text())
                        if len(r['steps'])!=len(oracle) or any(a['changed']!=b['changed'] or a['ruleset']!=b['ruleset'] or a['executed_bindings']!=b['executed_bindings']
                                                              for a,b in zip(r['steps'],oracle)):raise ValueError(case)
                        row={'inference_ms':1000*r['inference_seconds'],'load_setup_ms':1000*(r['load_seconds']+r['setup_seconds']),
                             'export_ms':1000*r['export_seconds']}
                        row['other_ms']=wall-sum(row.values())
                        phases={k:sum(s['phases'][k] for s in r['steps'])*1000 for k in r['steps'][0]['phases']}
                    else:
                        r=json.loads((dest/'run.json').read_text());assert r['finished'] and r['completed']==len(oracle)
                        row={'startup_ms':(r['entry_clock_ns']-start)/1e6,'load_setup_ms':r['setup_ms'],'inference_ms':r['inference_ms'],
                             'export_ms':r['total_ms']-r['setup_ms']-r['inference_ms']}
                        row['other_ms']=wall-sum(row.values())
                    row['wall_ms']=wall
                    if lane=='cpu':row.update({'cpu_'+k+'_ms':v for k,v in phases.items()})
                    if j>=0:samples[lane].append(row)
            print(case,j,flush=True)
        report[case]={lane:{'samples':rows,'medians':{k:median(s[k] for s in rows) for k in rows[0]},'export_sha256':expected[lane]} for lane,rows in samples.items()}
    output.write_text(json.dumps(report,indent=1)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('root','reference','weights','cpu','output'):p.add_argument(k,type=Path)
    a=p.parse_args();run(a.root,a.reference,a.weights,a.cpu.resolve(),a.output)

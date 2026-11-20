"""Run semantic audits first, then interleave clean cold CLIs with a resident producer per Pass."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
from statistics import median
import subprocess
import sys
from time import perf_counter

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
CASES = ('sum-bits','dot-product')

def read(p):
    return json.loads(p.read_bytes())

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def bench(reference,out):
    out.mkdir(parents=True,exist_ok=False)
    runtime = Path(os.environ.get('CARGO_TARGET_DIR', REPO/'target'))/'release/eggfuse-cell-runtime'
    def build(features):
        subprocess.run(['cargo','build','-p','eggfuse-cell-runtime','--release','--locked','--features',features],cwd=REPO,check=True)
        dest = out/features
        shutil.copy2(runtime,dest)
        return dest
    audited = build('gpu-bindings,slot-transfer-audit')
    plain = build('gpu-bindings')
    lanes={'cpu':[], 'pytorch':['--gpu-binding-python',sys.executable,'--gpu-binding-service',HERE/'service.py'],
           'native':['--gpu-binding-native'], 'retired':['--gpu-binding-native','--gpu-binding-retire'],
           'batched':['--gpu-binding-native','--gpu-binding-retire','--gpu-binding-batch']}
    study={}
    for case in CASES:
        oracle=reference/f'oracle-{case}'
        program=reference/case/'program.json'
        baseline=read(oracle/'report.json');steps=baseline['steps']
        def run(exe,lane,label):
            folder=out/f'{case}-{lane}-{label}'
            start=perf_counter()
            subprocess.run([exe,'--program',program,'--output',folder,*lanes[lane]],stdout=subprocess.DEVNULL,check=True)
            wall=1000*(perf_counter()-start)
            report=read(folder/'report.json')
            assert report['program_sha256']==baseline['program_sha256'] and report['status']=='complete'
            assert sha(folder/'state.json')==sha(oracle/'state.json')
            assert len(report['steps'])==len(steps)
            for a,b in zip(steps,report['steps']):
                for k in ('ordinal','ruleset','path','iterations','changed','executed_bindings'):
                    assert a[k]==b[k],(case,lane,k,a['ordinal'])
            if lane!='cpu':
                assert report['backend']=='cell-cpu-gpu-bindings' and report['gpu_bindings']['admitted_bindings']>0
            return folder,report,wall
        case_study={}
        for lane in lanes:
            folder,r,_=run(audited,lane,'audit')
            checks={}
            for name in ('rhs','writes','resumes'):
                actual=read(folder/(name+'.json'))
                expected=read(oracle/(name+'.json'))
                if actual!=expected:raise ValueError((case,lane,name,next(i for i,(a,b) in enumerate(zip(actual,expected),1) if a!=b)))
                assert len(actual)==len(steps)
                checks[name]={'runs':len(actual),'events':(sum(s['executed_bindings'] for s in steps) if name=='rhs' else sum(row[0] for row in actual)),'sha256':sha(folder/(name+'.json'))}
            case_study[lane]={'audit':checks,'state_sha256':sha(folder/'state.json'),'program_sha256':r['program_sha256'],'samples':[]}
        for i in range(-1,2*len(lanes)):
            order=list(lanes)
            if i>=len(order):order.reverse()
            for lane in order[i%len(order):]+order[:i%len(order)]:
                _,j,wall=run(plain,lane,i)
                if i<0:continue
                gpu=j.get('gpu_bindings',{})
                s=j['stats'];entry=j['entry_schedule'];e=entry['stats']
                row={'cli_ms':wall,'inference_ms':1000*j['inference_seconds'],'setup_ms':1000*j['setup_seconds'],
                     'gpu_query_batches':gpu.get('batches',0),'device_dispatches':gpu.get('device_dispatches',0),'tokens':gpu.get('tokens',0),'admitted':gpu.get('admitted_bindings',0),
                     'table_rows_packed':gpu.get('input_rows',0),'device_pairs':gpu.get('tested_pairs',0),
                     'request_bytes':gpu.get('request_bytes',0),'response_bytes':gpu.get('response_bytes',0),
                     'prepare_ms':1000*gpu.get('preparation_seconds',0),'exchange_ms':1000*gpu.get('exchange_seconds',0),
                     'service_ms':1000*gpu.get('service_seconds',0),'project_ms':1000*gpu.get('projection_seconds',0),
                     'retired_nodes':gpu.get('retired_entry_nodes',0),'eligible_rules':gpu.get('eligible_rules',0),
                     'residual_candidates':s['residual_candidates'],'direct_candidates':s['direct_candidates'],
                     'repaired_dependencies':s['repaired_dependencies'],'unions':s['unions'],'entry_packets':entry['live_packets'],
                     'seed_deliveries':e['consumer_seed_deliveries'],'node_notifications':e['node_notifications'],
                     'entry_decodes':e['row_decodes'],'parameter_copies':e['parameters_copied'],
                     'fact_decodes':j['fact_decode_calls'],'rhs_frames_avoided':s['rhs_frames_avoided']}
                row.update({k+'_ms':1000*sum(t['phases'][k] for t in j['steps']) for k in j['steps'][0]['phases']})
                case_study[lane]['samples'].append(row)
            print(case,i,flush=True)
        for data in case_study.values():
            samples=data['samples'];data['median']={k:median(v[k] for v in samples) for k in samples[0]}
        study[case]=case_study
        (out/'results.json').write_text(json.dumps(study,indent=1)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    bench(args.reference.resolve(),args.output.resolve())

"""Audit the native forward against PyTorch and the source engine, then pair resident policy on/off."""
import argparse
import hashlib
import json
from pathlib import Path
from statistics import median
import subprocess
import torch

from certificate import Generator
from export_cpu import export_inputs,export_model



def write(path,data):
    path.write_text(json.dumps(data,separators=(',',':'),allow_nan=False)+'\n')


def load(path):
    return json.loads(path.read_bytes())


def source_trace(report):
    return [tuple(step[k] for k in ('ordinal','ruleset','epoch','executed_bindings','changed')) for step in report['steps']]


def study(a):
    a.out.mkdir(parents=True,exist_ok=False)
    results={}
    for seed in (1703,1709):
        ck=a.weights/f'policy-{seed}.pt'
        model=a.out/f'model-{seed}.json';write(model,export_model(ck))
        for case in ('sum-bits','dot-product'):
            program=a.ref/case/'program.json';image=a.ref/f'release-input-{case}'
            plan=a.out/f'{case}-inputs.json'
            if not plan.exists():write(plan,export_inputs(program,image))
            generator=Generator(program,image,torch.load(ck,map_location='cpu',weights_only=True),'cpu')
            with torch.inference_mode():token=generator.emit()[1].cpu().numpy()
            sha=hashlib.sha256(token.tobytes()).hexdigest()
            counts={}
            for label,extra in [('assisted',[]),('autonomous',['--forest-only'])]:
                dest=a.out/f'{case}-{seed}-{label}'
                cmd=[a.binary,'--program',program,'--output',dest,'--forest-policy',model,'--forest-inputs',plan,'--audit-events',*extra]
                subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
                suffix='rust' if label=='assisted' else 'without-completion'
                gold=a.reference/f'{case}-{seed}-cpu-{suffix}'
                report=load(dest/'report.json');baseline=load(gold/'report.json')
                assert report['neural_policy']['certificate_sha256']==sha
                assert report['precomputed_forest']==baseline['precomputed_forest']
                assert source_trace(report)==source_trace(baseline)
                for field in ('state','rhs','resumes','writes','events'):
                    assert load(dest/f'{field}.json')==load(gold/f'{field}.json'),field
                forest=report['precomputed_forest']
                counts[label]=dict(runs=len(report['steps']),rhs=forest['rhs'],children=len(forest['children']),
                                   static_roots=len(forest['static']),certificate_sha256=sha,
                                   source_order_and_graph_equal=True)
            bench=subprocess.run([a.bench,program,model,plan],capture_output=True,text=True,check=True)
            paired=json.loads(bench.stdout)
            for arm in paired.values():arm['median_ms']=median(arm['samples_ms'])
            expected=counts['assisted']
            assert paired['with_policy']['neural_children']==expected['children']
            assert paired['with_policy']['rhs']==paired['exact']['rhs']==expected['rhs']
            results[f'{case}/{seed}']=dict(checks=counts,resident=paired)
            write(a.out/'results.json',results)
            print(case,seed,{k:round(v['median_ms'],2) for k,v in paired.items()},flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('binary','bench','ref','weights','reference','out'):parser.add_argument(key,type=Path)
    args=parser.parse_args()
    torch.set_num_threads(1)
    study(args)

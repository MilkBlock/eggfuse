"""Capture a reproducible train-only RHS corpus with per-Run reference audits.

Selection uses the existing split, binding count and saved CPU reference time,
never target accuracy or observed link counts. Raw artifacts stay outside Git.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import time
from collect_observed_corpus import read_bytes
from link_rhs_results import link
from summarize_rhs_results import summarize


def digest(raw):return hashlib.sha256(raw).hexdigest()


def select(manifest, max_bindings, max_cases):
    eligible=[e for e in manifest['cases'] if e['status']=='complete' and e['split']=='train'
              and e['summary']['observed_bindings']<=max_bindings]
    return sorted(eligible,key=lambda e:(e['summary']['observed_bindings'],e['case']))[:max_cases]


def main():
    p=argparse.ArgumentParser();p.add_argument('manifest',type=Path);p.add_argument('binary',type=Path)
    p.add_argument('output',type=Path);p.add_argument('--max-cases',type=int,default=3)
    p.add_argument('--max-bindings',type=int,default=2000);p.add_argument('--timeout',type=float,default=120)
    a=p.parse_args()
    if a.max_cases<1 or a.max_bindings<1 or a.timeout<=0:raise ValueError('positive limits required')
    manifest_bytes=a.manifest.read_bytes();manifest=json.loads(manifest_bytes)
    selected=select(manifest,a.max_bindings,a.max_cases)
    a.output.mkdir(parents=True,exist_ok=False)
    report=dict(schema='actual-rhs-training-corpus/v1',manifest_sha256=digest(manifest_bytes),
        binary_sha256=digest(a.binary.read_bytes()),partition='train',
        limits=dict(max_cases=a.max_cases,max_bindings=a.max_bindings,timeout=a.timeout,saved_reference_seconds=1),
        selection='smallest observed binding counts among complete train cases under limit',cases=[])
    totals=Counter()
    for e in selected:
        record=dict(case=e['case'],split=e['split'],program_sha256=e['program_sha256'])
        report['cases'].append(record);out=a.output/e['case'];out.mkdir()
        raw=read_bytes(Path(e['trace']))
        if digest(raw)!=e['trace_sha256']:raise ValueError('original trace hash mismatch')
        old=json.loads(raw);reference=old['reference_execution_seconds']
        if reference>1:
            record.update(status='skipped',reason='saved CPU reference exceeds 1 second')
            continue
        program_raw=read_bytes(Path(e['program']));program=json.loads(program_raw)
        if program['sha256']!=e['program_sha256'] or program['recipe']!=old['recipe']:
            raise ValueError('original program/trace mismatch')
        program_path=out/'program.json';program_path.write_bytes(program_raw)
        trace_path=out/'rhs.json';clock=time.monotonic()
        with (out/'capture.log').open('w') as log:
            try:
                proc=subprocess.run([str(a.binary.resolve()),str(program_path.resolve()),str(trace_path.resolve())],
                    stdout=log,stderr=subprocess.STDOUT,timeout=a.timeout)
            except subprocess.TimeoutExpired:
                record.update(status='timeout',wall_seconds=time.monotonic()-clock)
                print(json.dumps(record),flush=True);continue
        record['wall_seconds']=time.monotonic()-clock
        if proc.returncode:
            record.update(status='failed',returncode=proc.returncode)
            print(json.dumps(record),flush=True);continue
        captured_raw=trace_path.read_bytes();trace=json.loads(captured_raw)
        if trace['program_sha256']!=program['sha256'] or trace['recipe']!=program['recipe']:
            raise ValueError('captured program mismatch')
        summary=summarize(trace);links=link(trace)
        links['trace_sha256']=digest(captured_raw)
        links['corpus_partition']=dict(case=e['case'],split='train',manifest_sha256=report['manifest_sha256'])
        links_path=out/'links.json';links_path.write_text(json.dumps(links)+'\n')
        record.update(status='complete',trace_sha256=digest(captured_raw),links_sha256=digest(links_path.read_bytes()),
            trace=str(trace_path.resolve()),links=str(links_path.resolve()),capture=summary,link_counts=links['counts'])
        totals.update(links['counts'])
        print(json.dumps(dict(case=e['case'],status=record['status'],capture=summary['counts'],links=links['counts'])),flush=True)
        report['aggregate_link_counts']=dict(totals)
        (a.output/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    report['aggregate_link_counts']=dict(totals)
    report['completed_cases']=sum(e['status']=='complete' for e in report['cases'])
    report['limitations']=['Observed connection evidence only; no causal proof, ownership transfer or GPU takeover',
        'Only train partition; test and validation are never reassigned',
        'No ridge fitting or GPU inference in this data collection',
        'Capture wall includes full per-Run graph comparison; not a performance campaign']
    (a.output/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(completed=report['completed_cases'],counts=dict(totals))),flush=True)

if __name__=='__main__':main()

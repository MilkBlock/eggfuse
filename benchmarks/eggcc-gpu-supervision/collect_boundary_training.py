"""Collect actual GPU-generated contexts from independent training programs.

Select a boundary before the first Get continuation, never by validation score.
Reuse verified snapshots; keep unsupported/overflow outcomes in the manifest.
"""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
from collect_observed_corpus import read_bytes


def select_boundary(trace,rule=290):
    seconds=trace.get('reference_execution_seconds')
    if seconds is None or not 0<=seconds<=1:raise ValueError('not an authorized short reference workload')
    for run in trace['runs']:
        if any(b['rule']==rule for b in run['audit']['bindings']):
            if run['ordinal']<1:raise ValueError('missing preceding boundary')
            return run['ordinal']-1
    raise ValueError('no selected continuation')


def main():
    p=argparse.ArgumentParser()
    for key in ('training','corpus','binary','model','artifacts','output'):p.add_argument(key,type=Path)
    p.add_argument('--cases',default='049-dead-branch,033-sum-check,035-sum-sq-diff');a=p.parse_args()
    manifest=json.loads(a.training.read_text());corpus_raw=a.corpus.read_bytes();corpus=json.loads(corpus_raw)
    if manifest['partition']!='train' or manifest['manifest_sha256']!=hashlib.sha256(corpus_raw).hexdigest():raise ValueError('training provenance')
    entries={c['case']:c for c in manifest['cases']};originals={c['case']:c for c in corpus['cases']}
    names=a.cases.split(',')
    if not names or len(set(names))!=len(names) or any(n not in entries or n not in originals for n in names):raise ValueError('invalid case selection')
    a.artifacts.mkdir(parents=True,exist_ok=True);results=[]
    for name in names:
        item=entries[name];source=originals[name]
        if item['status']!='complete' or item['split']!='train' or source['split']!='train':raise ValueError('non-training source')
        raw=read_bytes(Path(item['trace']))
        if hashlib.sha256(raw).hexdigest()!=item['trace_sha256']:raise ValueError('trace hash')
        trace=json.loads(raw);at=select_boundary(trace)
        program_raw=read_bytes(Path(source['program']));program=json.loads(program_raw)
        if program['sha256']!=item['program_sha256'] or program['recipe']!=trace['recipe']:raise ValueError('program identity')
        stem=a.artifacts/name;input_path=stem.with_suffix('.program.json');snap=stem.with_suffix('.trace.json')
        execution=stem.with_suffix('.execution.json');capture=stem.with_suffix('.npz');labeled=stem.with_suffix('.labeled.npz');labels=stem.with_suffix('.labels.json')
        input_path.write_bytes(program_raw)
        commands=[]
        if snap.exists():
            saved=json.loads(snap.read_text())
            if saved['program_sha256']!=program['sha256'] or saved['recipe']!=program['recipe'] or not all(saved.get(k) is True for k in ('strict_run_graphs_equal','strict_audit_reference_equal','run_control_counts_equal')) or sum(b['ordinal']==at for b in saved['boundaries'])!=1:raise ValueError('cached snapshot provenance')
        else:commands.append([str(a.binary),str(input_path),str(snap),'--snapshot-runs='+str(at)])
        commands.extend([
            [sys.executable,str(Path(__file__).with_name('audit_construct_union_family.py')),str(snap),str(a.model),str(execution),'--rules','283,290,293','--snapshot-run',str(at),'--ticks','24','--flush-every','1','--order-queries','--boundary-context','--capture',str(capture)],
            [sys.executable,str(Path(__file__).with_name('label_composed_witnesses.py')),str(capture),str(snap),str(a.model),str(a.corpus),str(labeled),str(labels),'--snapshot-run',str(at)]])
        record=dict(case=name,partition='train',snapshot_run=at,reference_seconds=trace['reference_execution_seconds'],source_trace_sha256=item['trace_sha256'],status='passed',commands=commands)
        for i,cmd in enumerate(commands):
            with stem.with_suffix('.step'+str(i)+'.log').open('w') as log:
                result=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
            if result.returncode:
                record.update(status='needs_investigation',failed_command=i,exit_code=result.returncode);break
        if record['status']=='passed':
            ex=json.loads(execution.read_text());lab=json.loads(labels.read_text())
            if not ex['passed'] or not lab['passed'] or lab['partition']!='train':raise ValueError('acceptance')
            record.update(samples=lab['samples'],generated_sources=lab['continued_samples'],labeled=str(labeled),sha256=lab['artifact_sha256'],execution=str(execution))
        results.append(record);print(json.dumps(record),flush=True)
        a.output.write_text(json.dumps(dict(scope='real GPU boundary-context training collection, not full Eggcc',records=results,expected_cases=names,passed=len(results)==len(names) and all(r['status']=='passed' for r in results),binary_sha256=hashlib.sha256(a.binary.read_bytes()).hexdigest()),indent=2)+'\n')
    if not all(r['status']=='passed' for r in results):raise SystemExit(1)

if __name__=='__main__':main()

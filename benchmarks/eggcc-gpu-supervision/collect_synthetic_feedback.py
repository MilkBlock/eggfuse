"""Actual GPU predicted-source trajectories on synthetic-only inputs."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
from synthetic_cell_inputs import validate


def main():
    p=argparse.ArgumentParser()
    for k in ('inputs','model','head','head_report','output'):p.add_argument(k,type=Path)
    a=p.parse_args();manifest=json.loads((a.inputs/'manifest.json').read_text());a.output.mkdir(parents=True,exist_ok=True)
    records=[];head_hash=hashlib.sha256(a.head.read_bytes()).hexdigest()
    report=json.loads(a.head_report.read_text())
    if report['head_sha256']!=head_hash or not report.get('synthetic_only_training'):raise ValueError('synthetic-only parent head required')
    for item in manifest['records']:
        if item['status']!='complete':
            records.append(dict(source=item,status='source_rejected'));continue
        name=item.get('case',str(item.get('seed')));source=a.inputs/(name+'.json')
        validate(json.loads(source.read_text()));stem=a.output/name;capture=stem.with_suffix('.capture.npz')
        commands=[
          [sys.executable,str(Path(__file__).with_name('audit_construct_union_family.py')),str(source),str(a.model),str(stem.with_suffix('.execution.json')),
           '--synthetic-input','--rules','0,1,2','--snapshot-run','0','--capacity','32','--ticks','20','--flush-every','1','--order-queries','--boundary-context','--experimental-boundary-model','--predicted-source-feedback','--completion-classifier',str(a.head),'--completion-classifier-report',str(a.head_report),'--capture',str(capture)],
          [sys.executable,str(Path(__file__).with_name('label_composed_witnesses.py')),str(capture),str(source),str(a.model),'/dev/null',str(stem.with_suffix('.labeled.npz')),str(stem.with_suffix('.labels.json')),'--synthetic-input','--snapshot-run','0','--completion-classifier',str(a.head)]]
        record=dict(case=name,status='passed',source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),commands=commands)
        for i,cmd in enumerate(commands):
            with stem.with_suffix('.step'+str(i)+'.log').open('w') as f:result=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
            if result.returncode:
                record.update(status='failed',command=i,exit_code=result.returncode);break
        if record['status']=='passed':
            e=json.loads(stem.with_suffix('.execution.json').read_text());l=json.loads(stem.with_suffix('.labels.json').read_text())
            if not e['passed'] or not l['passed'] or not l.get('synthetic_input'):raise ValueError('feedback audit')
            record.update(samples=l['samples'],generated_sources=l['continued_samples'],labeled=str(stem.with_suffix('.labeled.npz')),artifact_sha256=l['artifact_sha256'])
        records.append(record)
        (a.output/'manifest.json').write_text(json.dumps(dict(scope='synthetic GPU feedback collection, exact execution remains authoritative',parent_head_sha256=head_hash,records=records),indent=2)+'\n')
        print(json.dumps(record),flush=True)
        if record['status']=='failed':raise SystemExit(1)

if __name__=='__main__':main()

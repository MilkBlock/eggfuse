"""Collect actual device-selected witnesses with workload partition provenance."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
from collect_observed_corpus import read_bytes


def main():
    p=argparse.ArgumentParser()
    for name in ('training','validation','corpus','model','artifacts','report'):p.add_argument(name,type=Path)
    p.add_argument('--per-partition',type=int,default=1);a=p.parse_args()
    if a.per_partition<1:raise ValueError('positive case budget')
    corpus_sha=hashlib.sha256(a.corpus.read_bytes()).hexdigest();records=[]
    a.artifacts.mkdir(parents=True,exist_ok=True)
    for split,path in [('train',a.training),('validation',a.validation)]:
        manifest=json.loads(path.read_text())
        if manifest['partition']!=split or manifest['manifest_sha256']!=corpus_sha:raise ValueError('corpus partition mismatch')
        cases=[c for c in manifest['cases'] if c['status']=='complete'][:a.per_partition]
        for case in cases:
            if case['split']!=split or hashlib.sha256(read_bytes(Path(case['trace']))).hexdigest()!=case['trace_sha256']:raise ValueError('trace provenance')
            name=Path(case['case']).name;prefix=a.artifacts/(split+'-'+name)
            result=prefix.with_suffix('.result.json');archive=prefix.with_suffix('.npz')
            process=subprocess.run([sys.executable,str(Path(__file__).with_name('audit_type_family.py')),case['trace'],str(a.model),str(result),
                '--capture',str(archive),'--corpus-manifest',str(a.corpus)],capture_output=True,text=True)
            prefix.with_suffix('.log').write_text(process.stdout+process.stderr)
            if process.returncode:
                records.append(dict(case=name,partition=split,status='needs_cpu_or_investigation',exit_code=process.returncode));continue
            data=json.loads(result.read_text())
            if not data['passed'] or data['capture']['partition']!=split or data['trace_sha256']!=case['trace_sha256']:raise ValueError('capture acceptance/provenance')
            records.append(dict(case=name,partition=split,status='verified',capture=str(archive),result=str(result),
                trace_sha256=data['trace_sha256'],**{k:data['capture'][k] for k in ('samples','continued_samples','relocated_witness_observations','artifact_sha256','logical_array_bytes','padded_capture_array_bytes','cpu_audit_and_prepare_seconds')}))
            print(json.dumps(records[-1]),flush=True)
    totals={split:sum(c.get('samples',0) for c in records if c['partition']==split) for split in ('train','validation')}
    out=dict(scope='real four-rule Cell-family GPU witness corpus, not full Eggcc or trained accuracy',corpus_manifest_sha256=corpus_sha,
        model_sha256=hashlib.sha256(a.model.read_bytes()).hexdigest(),records=records,samples_by_partition=totals,
        passed=bool(records) and all(c['status']=='verified' for c in records),backpropagation=False,
        limitations=['Final snapshots with selected derived tables removed, not original initialization','Only four type-analysis rules',
            'No model fitting here; split labels retained for downstream training','CPU targets independently computed after device execution'])
    a.report.write_text(json.dumps(out,indent=2)+'\n')
    if not out['passed']:raise SystemExit(1)

if __name__=='__main__':main()

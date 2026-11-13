"""Native verification of every actual GPU pair prediction in a frozen corpus."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from native_audit_report import summarize


def main():
    p=argparse.ArgumentParser();p.add_argument('manifest',type=Path);p.add_argument('predictions',type=Path);p.add_argument('proposals',type=Path);p.add_argument('output',type=Path);p.add_argument('--binary',type=Path,default=Path('target/debug/examples/native_proof_audit'));args=p.parse_args()
    manifest=json.loads(args.manifest.read_text());predictions=json.loads(args.predictions.read_text())
    if [c['case'] for c in manifest['cases']]!=[c['case'] for c in predictions['cases']]:raise ValueError('workload mismatch')
    reports=[]
    with tempfile.TemporaryDirectory(prefix='cell-native-audit-') as tmp:
        for case,pred in zip(manifest['cases'],predictions['cases']):
            path=Path(case['trace']);target=Path(tmp)/(case['case']+'.json')
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            if digest!=case['trace_sha256'] or digest!=pred['trace_sha256']:raise ValueError('trace checksum changed')
            if case['program_sha256']!=pred['program_sha256']:raise ValueError('program checksum mismatch')
            proc=subprocess.run([str(args.binary),str(path.parent/'program.json'),str(target),str(args.proposals/(case['case']+'.json'))],capture_output=True,text=True,timeout=120)
            if not target.exists():raise RuntimeError(proc.stderr)
            audit=json.loads(target.read_text())
            if proc.returncode!=(0 if audit['pass'] else 1):raise RuntimeError(proc.stderr)
            summary=summarize(json.loads(path.read_text()),audit)
            counts=summary['counts']['all'];metrics=pred['metrics']
            for actual,expected in [('checked_pairs','pairs'),('true_positives','tp'),('false_positives','fp'),('false_negatives','fn')]:
                if counts[actual]!=metrics[expected]:raise ValueError((case['case'],actual,counts,metrics))
            if counts['invalid_claims']:raise ValueError('invalid proposal address')
            # The corpus split, not the generic report's per-trace 60/20/20 split,
            # defines training and holdout here.
            summary['counts']=counts;summary.update(case=case['case'],split=case['split'])
            reports.append(summary)
    args.output.write_text(json.dumps(dict(scope='native runtime checking of saved Metal predictions, not GPU commits',all_gpu_counts_match_native=True,cases=reports),indent=2)+'\n')

if __name__=='__main__':main()

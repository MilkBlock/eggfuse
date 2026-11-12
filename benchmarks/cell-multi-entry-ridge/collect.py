"""Run independent short cases; never silently skip a timeout or failed proof."""
import argparse
import hashlib
import json
import subprocess
import tempfile
import time
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--runner',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--timeout',type=float,default=1.0);args=p.parse_args()
    source=json.loads(args.inputs.read_text());cases=[];seconds=[]
    with tempfile.TemporaryDirectory(prefix='cell-multi-entry-') as tmp:
        request=Path(tmp)/'input.json';result=Path(tmp)/'output.json'
        for case in source['cases']:
            request.write_text(json.dumps(dict(cases=[case])))
            start=time.perf_counter()
            subprocess.run([str(args.runner.resolve()),str(request),str(result)],check=True,
                           timeout=args.timeout,capture_output=True,text=True)
            seconds.append(time.perf_counter()-start)
            rows=json.loads(result.read_text())['cases']
            assert len(rows)==1 and rows[0]['id']==case['id']
            assert rows[0]['fixed_point']['status']=='pass'
            if case.get('native_reference'):assert 'native_final' in rows[0]
            cases.extend(rows)
    report=dict(schema='eggfuse.real-completion-dataset.v1',cases=cases,
                collection=dict(inputs_sha256=hashlib.sha256(args.inputs.read_bytes()).hexdigest(),
                                runner_sha256=hashlib.sha256(args.runner.read_bytes()).hexdigest(),
                                timeout_seconds=args.timeout,case_seconds=seconds,
                                timing_scope='Timeout enforcement only, not a performance benchmark'))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n');print('collected',len(cases))


if __name__=='__main__':main()

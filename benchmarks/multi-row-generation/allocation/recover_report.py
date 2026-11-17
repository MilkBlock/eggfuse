"""Recover reporting-only JSON failure from saved final outputs; no training."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np
from data import audit


def main():
    p=argparse.ArgumentParser();p.add_argument('artifact',type=Path);p.add_argument('log',type=Path);a=p.parse_args()
    if (a.artifact/'result.json').exists():raise RuntimeError('will not overwrite a report')
    protocol=json.loads((a.artifact/'protocol.json').read_text());history=[]
    for line in a.log.read_text().splitlines():
        if line.startswith('{"step"'):history.append(json.loads(line))
    assert history[-1]['step']==protocol['steps'];reports={}
    expected=8 if protocol['mode']=='joint' else 4
    for path in sorted(a.artifact.glob('*.npz')):
        with np.load(path,allow_pickle=False) as z:
            r=audit(z['a'],z['b'],z,z['source_pos']);assert r['complete_graphs']==int(z['gpu_pass'].sum());assert z['finite'].all();reports[path.stem]=r
    assert len(reports)==expected
    result=dict(protocol=protocol,training=history,panels=reports,
        status='pass' if all(v['complete_graphs']==v['graphs'] for k,v in reports.items() if not k.endswith('-cut')) else 'difference',
        model_sha256=hashlib.sha256((a.artifact/'model.safetensors').read_bytes()).hexdigest(),cpu_inference_corrections=0,
        scope='unanchored equality-join set generation; one neural stage, not recurrence or full egraph inference',
        reporting_recovery='Original final report JSON serialization rejected NumPy count scalar; recovered from saved final outputs and original training log, without rerunning model/training.',
        recovery_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (a.artifact/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'],{k:v['complete_graphs'] for k,v in reports.items()})

if __name__=='__main__':main()

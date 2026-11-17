"""CPU-only token, binding and whole-set replay, without model execution."""
import argparse,json,hashlib,sys
from pathlib import Path
import numpy as np
from stream_metrics import check_token,repeat_metrics
from metrics import soft_metrics
from data import audit


def main():
    p=argparse.ArgumentParser();p.add_argument('artifact',type=Path);a=p.parse_args();report=json.loads((a.artifact/'result.json').read_text())
    assert report['model_sha256']==hashlib.sha256((a.artifact/'model.safetensors').read_bytes()).hexdigest();panels={}
    for path in sorted(a.artifact.glob('*.npz')):
        with np.load(path,allow_pickle=False) as z:
            length=int(z['source_pos'][:,1].max())+1;check_token(z,z['source_pos']);r=audit(z['a'],z['b'],z,z['source_pos'])
            r['soft']=soft_metrics(z['a'],z['b'],z);r['repeats']=repeat_metrics(z,length);panels[path.stem]=r
    assert json.loads(json.dumps(panels))==report['panels'];assert 'mlx.core' not in sys.modules
    print(json.dumps(dict(model_sha256=report['model_sha256'],panels=panels),indent=2))
    if any(r['complete_graphs']!=r['graphs'] for k,r in panels.items() if not k.endswith(('-erase','-local'))):raise SystemExit(1)

if __name__=='__main__':main()

"""CPU-only replay of actually generated set tokens; no network, no repair."""
import argparse,json,hashlib,sys
from pathlib import Path
import numpy as np
from data import audit


def main():
    p=argparse.ArgumentParser();p.add_argument('artifact',type=Path);a=p.parse_args();meta=json.loads((a.artifact/'result.json').read_text())
    assert hashlib.sha256((a.artifact/'model.safetensors').read_bytes()).hexdigest()==meta['model_sha256'];reports={}
    for path in sorted(a.artifact.glob('*.npz')):
        with np.load(path,allow_pickle=False) as z:
            reports[path.stem]=audit(z['a'],z['b'],z,z['source_pos'])
            assert json.loads(json.dumps(reports[path.stem]))==meta['panels'][path.stem];assert z['finite'].all()
    assert 'mlx.core' not in sys.modules
    print(json.dumps(dict(model_sha256=meta['model_sha256'],panels=reports),indent=2))
    if any(r['complete_graphs']!=r['graphs'] for k,r in reports.items() if not k.endswith('-cut')):raise SystemExit(1)

if __name__=='__main__':main()

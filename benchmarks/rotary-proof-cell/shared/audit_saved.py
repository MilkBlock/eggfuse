"""Independent NumPy-only audit of actual saved structured-token bytes."""
import argparse,json,sys
from pathlib import Path
import numpy as np
from fresh import register
from cpu_contract import audit
p=argparse.ArgumentParser();p.add_argument('checkpoint',type=Path);a=p.parse_args()
protocol=json.loads((a.checkpoint.parent/'protocol.json').read_text())
register(protocol['fresh_manifest'])
assert 'mlx.core' not in sys.modules
with np.load(a.checkpoint,allow_pickle=False) as d:r=audit(d['cases'],d['positions'],d)
print(json.dumps(r,indent=2));sys.exit(0 if r['passed']==r['cases'] else 1)

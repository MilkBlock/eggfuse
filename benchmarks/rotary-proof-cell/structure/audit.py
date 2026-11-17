"""NumPy-only post-hoc replay; returns failure without repairing latent or output."""
import argparse,json,sys
import numpy as np
from semantics import audit
p=argparse.ArgumentParser();p.add_argument('checkpoint');args=p.parse_args()
with np.load(args.checkpoint,allow_pickle=False) as d:
    r=audit(d['cases'],d['positions'],d,d['decoder_weight'],d['decoder_bias'])
print(json.dumps(r,indent=2))
sys.exit(0 if r['passed']==r['cases'] else 1)

"""Confirm reused controls reproduce prior hard outputs and shared fresh inputs."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args();old=a.root.parent/'multi-row-allocation-20261118';checks=[];fresh_hashes=None
    for path in sorted(a.root.iterdir()):
        if not (path/'result.json').exists():continue
        r=json.loads((path/'result.json').read_text());h=r['protocol']['final_input_hashes']
        if fresh_hashes is None:fresh_hashes=h
        else:assert fresh_hashes==h
        if r['protocol']['treatment']!='control':continue
        prior=old/f"{r['protocol']['mode']}-{r['protocol']['seed']}"
        assert hashlib.sha256((path/'model.safetensors').read_bytes()).digest()==hashlib.sha256((prior/'model.safetensors').read_bytes()).digest()
        for panel in ('iid','multiplicity'):
            for layout in ('4x2','2x4'):
                name=panel+'-'+layout+'.npz'
                with np.load(path/name) as x,np.load(prior/name) as y:
                    for k in ('a','b','source_pos','active','pointers','fields','addresses','gpu_pass'):np.testing.assert_array_equal(x[k],y[k])
                checks.append(str(path.name+'/'+name))
    assert len(checks)==16
    print(json.dumps(dict(controls_reproduced=checks,fresh_input_hashes=fresh_hashes,status='pass'),indent=2))

if __name__=='__main__':main()

"""Create a relocatable research bundle for the measured frozen CPU policy."""
import argparse
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import numpy as np

HERE=Path(__file__).resolve().parent;GPU=HERE.parent
sys.path.insert(0,str(GPU/'joint-witness'))
spec=importlib.util.spec_from_file_location('lower_cpu_bundle',GPU/'joint-witness/prepare.py')
joint=importlib.util.module_from_spec(spec);spec.loader.exec_module(joint)


def save(p,x):p.write_text(json.dumps(x,separators=(',',':'))+'\n')


def freeze(program,image,native,out,seed):
    if out.exists():raise FileExistsError(out)
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent) as tmp:
        work=Path(tmp)/'bundle'
        joint.prepare(SimpleNamespace(program=program,image=image,out=work,policy='certified',seed=seed))
        model=joint.read(work/'multi.json')
        tied=((np.asarray(model['q'],np.float32)+np.asarray(model['k'],np.float32))*np.float32(.5)).tolist()
        save(work/'multi.json',dict(model,q=tied,k=tied))
        subprocess.run([native,'--bake-port-codes',work/'multi.json',work/'ports.bin'],check=True)
        save(work/'root.json',dict(control='use',forbid_fallback=True,encoding='checked_slots'))
        merge=joint.read(work/'merge.json');save(work/'merge.json',dict(merge,allow_empty=True))
        request=joint.read(work/'request.json')
        request.update(joint.read(HERE/'frozen-options.json'),baked_codes='ports.bin')
        save(work/'request.json',request)
        files={p.name:sha256(p.read_bytes()).hexdigest() for p in sorted(work.iterdir())}
        save(work/'bundle-manifest.json',dict(format='eggfuse.cpu-bundle/v1',profile=request['cpu_profile'],seed=seed,files=files))
        work.rename(out)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('program','image','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--seed',type=int,choices=(1703,1709),default=1703)
    a=p.parse_args();freeze(a.program,a.image,a.native.resolve(),a.out,a.seed)

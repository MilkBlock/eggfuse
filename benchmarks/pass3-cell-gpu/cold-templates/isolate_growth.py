"""Send a growing-library checkpoint and a compiled program to the isolated existing full-Pass-3 entrypoint."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from policy import read,HERE
from capture import inputs,load_catalog,verify
from isolate import sha


def main(a):
    a.out.mkdir(parents=True,exist_ok=False);result={}
    for case in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax'):
        image,program,gold=inputs(a.corpus,a.ref,case);entries=load_catalog(image,program,a.ref/'sum-bits/program.json')
        for kind in ('id','graph','compose'):
            for seed in (1703,1709):
                checkpoint=a.models/f'{kind}-{seed}-train40'/'cache-64.json'
                policy=read(checkpoint)
                with tempfile.TemporaryDirectory() as temp:
                    root=Path(temp).resolve()
                    for name in ('device.json','device.npz'):shutil.copyfile(image/name,root/name)
                    for src,name in [(checkpoint,'actor.json'),(a.ref/'ports-1703.pt','ports.pt'),(a.reader,'reader.pt')]:
                        shutil.copyfile(src,root/name)
                    static=dict(schema='eggfuse.compound-catalog/v1',image_sha256=sha(root/'device.json'),entries=entries,joins=policy['joins'])
                    (root/'catalog.json').write_text(json.dumps(static))
                    subprocess.run([sys.executable,str(HERE.parent/'recurrent-generator/isolate.py'),root,a.ref.parent,
                                    'unused','unused','unused','--worker'],check=True)
                    opened=read(root/'opened.json');assert set(opened)=={'device.json','device.npz','actor.json','ports.pt','reader.pt','catalog.json'}
                    dest=root/'output';verify(dest,gold,image)
                    baseline=a.paired/f'{case}-{seed}-64-{kind}'
                    for filename,fields in [('neural-output.npz',('raw','rhs_ordinal','verdict')),('compound-output.npz',('claims',))]:
                        with np.load(dest/filename) as z,np.load(baseline/filename) as b:
                            for f in fields:np.testing.assert_array_equal(z[f],b[f])
                    result[f'{case}/{seed}/{kind}']=dict(opened=opened,source_aligned=True,
                                                         roles=read(dest/'run.json')['execution_roles'])
                (a.out/'results.json').write_text(json.dumps(result,indent=1)+'\n')
    print(len(result),'isolated largest-library evaluations',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','reader','models','paired','out'):p.add_argument(k,type=Path)
    main(p.parse_args())

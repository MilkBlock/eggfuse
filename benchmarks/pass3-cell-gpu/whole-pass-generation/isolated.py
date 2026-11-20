"""Expose only the static source packet and frozen weights to the online process."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def worker(root,forbidden,completion):
    seen=set()
    def check(event,args):
        if event!='open' or not isinstance(args[0],str):return
        path=Path(args[0]).resolve()
        if path.is_relative_to(forbidden):raise RuntimeError(f'online reference access: {path}')
        if path.parent==root:seen.add(path.name)
    sys.addaudithook(check)
    import torch
    from study import open_generator
    from adapter import specialize
    from policy import load_packet
    p=load_packet(root/'forest-plan.npz',root)
    ck=torch.load(root/'model.pt',weights_only=True)
    emit,saved=open_generator(p,ck,'learned')
    with torch.inference_mode():
        specialize(p,emit,completion)(root/'device.json',root/'reader.pt',root/'ports.pt',2048,2,root/'output')
    tokens=saved[0].cpu().numpy()
    import numpy as np
    np.save(root/'output'/'raw.npy',tokens)
    (root/'output'/'opened.json').write_text(json.dumps(sorted(seen)))


def main(a):
    from study import audit,inputs,verify,packet,read
    import numpy as np
    from policy import save_packet
    a.out.mkdir(parents=True,exist_ok=False)
    report={}
    for n in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax'):
        image,program,source=inputs(a.corpus,a.ref,n);p=packet(image,program)
        for seed in (1703,1709):
            pair={}
            for residual in (False,True):
                with tempfile.TemporaryDirectory() as t:
                    root=Path(t).resolve()
                    # The wrapper usually sets TMPDIR under /Volumes/.../tmp, outside the forbidden experiment tree.
                    if root.is_relative_to(a.ref.parent.resolve()):raise ValueError('isolation directory overlaps experiment tree')
                    save_packet(p,root/'forest-plan.npz')
                    for name in ('device.json','device.npz'):shutil.copyfile(image/name,root/name)
                    for path,name in [(a.reader,'reader.pt'),(a.ref/'ports-1703.pt','ports.pt'),
                                      (a.weights/f'policy-{seed}.pt','model.pt')]:
                        shutil.copyfile(path,root/name)
                    subprocess.run([sys.executable,__file__,'--worker',str(root),str(a.ref.parent.resolve()),
                                    *(['--completion'] if residual else [])],check=True)
                    dest=root/'output'
                    seen=read(dest/'opened.json')
                    assert set(seen)=={'device.json','device.npz','forest-plan.npz','model.pt','reader.pt','ports.pt'}
                    tokens=np.load(dest/'raw.npy')
                    stats=audit(dest,source,p,tokens,residual)
                    if residual:verify(dest,source,image)
                    pair['assisted' if residual else 'no_residual']=dict(opened=seen,
                            sha256=hashlib.sha256(tokens.tobytes()).hexdigest(),child_winners=stats['child_winners'],
                            static_roots=stats['static_roots'],exact_residual=stats['exact_residual'],first_divergence=stats['first_divergence'])
            assert pair['assisted']['sha256']==pair['no_residual']['sha256']
            report[f'{n}/{seed}']=pair
            (a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--worker',nargs=2,type=Path)
    ap.add_argument('--completion',action='store_true')
    for k in ('corpus','ref','reader','weights','out'):ap.add_argument(k,nargs='?',type=Path)
    a=ap.parse_args()
    if a.worker:worker(*a.worker,a.completion)
    else:main(a)

"""Copy only the compiled image/weights. The worker denies access to every experiment and reference file."""
import argparse,hashlib,json,shutil,subprocess,sys,tempfile
from pathlib import Path
from catalog import load_catalog,read
HERE=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def worker(root,forbid,completion):
    opened=set()
    def hook(event,args):
        if event!='open' or not isinstance(args[0],str):return
        p=Path(args[0]).resolve()
        if p.is_relative_to(forbid):raise ValueError(f'online reference access {p}')
        if p.parent==root:opened.add(p.name)
    sys.addaudithook(hook)
    from online import run
    run(root/'device.json',root/'reader.pt',root/'ports.pt',root/'catalog.json',root/'actor.json',root/'output',completion)
    (root/'opened.json').write_text(json.dumps(sorted(opened)))
if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('corpus','ref','reader','capture','out'):p.add_argument(k,type=Path)
    p.add_argument('--worker',action='store_true');p.add_argument('--no-exact',action='store_true');a=p.parse_args()
    if a.worker:worker(a.corpus.resolve(),a.ref.resolve(),not a.no_exact);sys.exit()
    from capture import inputs,verify
    import numpy as np
    a.out.mkdir(parents=True,exist_ok=False);report={}
    for n in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax'):
        image,program,gold=inputs(a.corpus,a.ref,n);r={}
        for residual in (False,True):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp).resolve()
                for name in ('device.json','device.npz'):shutil.copyfile(image/name,root/name)
                for path,name in [(a.reader,'reader.pt'),(a.ref/'ports-1703.pt','ports.pt'),(a.capture/'train-1703/actor.json','actor.json')]:
                    shutil.copyfile(path,root/name)
                entries=load_catalog(image,program,a.ref/'sum-bits/program.json')
                (root/'catalog.json').write_text(json.dumps(dict(schema='eggfuse.leaf-catalog/v1',entries=entries,image_sha256=sha(image/'device.json'))))
                subprocess.run([sys.executable,__file__,root,a.ref.parent,'unused','unused','unused','--worker',*([] if residual else ['--no-exact'])],check=True)
                seen=read(root/'opened.json');assert set(seen)=={'device.json','device.npz','reader.pt','ports.pt','catalog.json','actor.json'}
                dest=root/'output';observed=read(dest/'run.json')
                if residual:verify(dest,gold,image)
                with np.load(dest/'output.npz') as z,np.load(gold/'output.npz') as w:
                    length=min(len(z['runs']),len(w['runs']))
                    first=next((i+1 for i in range(length) if not np.array_equal(z['runs'][i,[0,1,2,3]],w['runs'][i,[0,1,2,3]])),None)
                    r['assisted' if residual else 'neural_only']=dict(opened=seen,source_runs=len(w['runs']),actual_runs=len(z['runs']),
                        source_rhs=len(w['rhs']),actual_rhs=len(z['rhs']),first_schedule_or_count_difference=first,
                        roles=observed['execution_roles'],device_stopped=observed['finished'])
                    if not residual:assert first is not None and observed['execution_roles']['rhs_inputs_from_exact_search']==0
        report[n]=r;(a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')

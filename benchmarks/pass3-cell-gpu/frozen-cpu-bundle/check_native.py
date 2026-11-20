"""Compare the source-only Rust compiler with the independent Python lowering and native CPU oracle."""
import argparse,hashlib,json,os,shutil,subprocess,tempfile
from pathlib import Path
from time import perf_counter_ns
import numpy as np
from prepare import freeze
from check import cli


def bits32(value):
    return np.asarray(value, dtype=np.float32).view(np.uint32)

CASES=('sum-bits','dot-product','jacobi-1d','conjugate-gradient','3mm','deriche','pair')
def locations(exp,name):
    if name in ('sum-bits','dot-product'):
        root=exp/'pass3-atlas-integration-20261120'
        return root/name/'program.json',root/('release-input-'+name)
    if name=='pair':
        root=exp/'complete-generation-edge-v5/two'
        return root/'compiled/program.json',root/'image'
    root=exp/('compact-holdouts-20261121-v1' if name in ('jacobi-1d','conjugate-gradient') else 'extra-pass3-transfer-v1')
    return root/name/'program.json',root/(name+'-image')


def run(a):
    a.out.mkdir(parents=True,exist_ok=False);results={}
    env={k:v for k,v in os.environ.items() if not k.startswith('EGGFUSE_')}
    for name in a.cases:
        program,image=locations(a.exp,name);folder=a.out/name;folder.mkdir();source=folder/'program only.json';shutil.copyfile(program,source)
        for seed in ((1703,1709) if name in ('sum-bits','pair') else (1703,)):
            path=folder/f'rust-{seed}';py=folder/f'python-{seed}'
            with tempfile.TemporaryDirectory() as cwd:
                start=perf_counter_ns()
                cmd=[a.native,'--compile-bundle',source,path,str(seed)]
                subprocess.run(cmd,cwd=cwd,env=env,check=True)
                native_ms=(perf_counter_ns()-start)/1e6
                start=perf_counter_ns();freeze(program,image,a.native,py,seed);python_ms=(perf_counter_ns()-start)/1e6
                assert (py/'program.json').read_bytes()==(path/'program.json').read_bytes()
                plans=(path/'plans.json').read_bytes()
                assert plans==(py/'plans.json').read_bytes(),name
                assert (py/'ports.bin').read_bytes()==(path/'ports.bin').read_bytes()
                for file in ('request.json','root.json'):
                    assert json.loads((path/file).read_bytes())==json.loads((py/file).read_bytes()),(name,file)
                for file,key in [('single.json','model'),('multi.json','q'),('multi.json','k'),('merge.json','weights')]:
                    x=json.loads((path/file).read_bytes())[key];y=json.loads((py/file).read_bytes())[key]
                    if isinstance(x,dict):
                        assert x.keys()==y.keys()
                        for f in x:
                            assert np.array_equal(bits32(x[f]),bits32(y[f])),(name,file,f)
                    else:assert np.array_equal(bits32(x),bits32(y)),(name,file,key)
                gold=json.loads(subprocess.run([a.exp/'compact-vanilla-20261121/vanilla',program],input='{}\n',text=True,capture_output=True,check=True).stdout)
                q=cli(a.native,'--bundle',path,cwd);assert not q.returncode,(name,q.stderr,q.stdout[-300:])
                v=json.loads(q.stdout)
                assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs'] and v['neural_rhs']==v['rhs']==gold['rhs_count']
                proof=v['profile_execution'];assert proof['views']==2 and proof['sealed_before_verifier'] and proof['sealed_tuples']==v['multi_raw_tuples']
                row=dict(program_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),rules=len(json.loads(plans)),active_plans=sum(p is not None for p in json.loads(plans)),
                         plan_sha256=hashlib.sha256(plans).hexdigest(),table_sha256=hashlib.sha256((path/'ports.bin').read_bytes()).hexdigest(),
                         native_compile_ms=native_ms,python_reference_ms=python_ms,source_rhs=v['rhs'],runs=v['runs'],state=v['state_sha'],
                         profile_execution=proof)
                # Both command forms exercise the actual same graph verifier on representative nonempty schedules.
                if name in ('sum-bits','pair'):
                    audited=cli(a.native,'--audit-bundle',path,cwd);assert audited.returncode==0
                    out=json.loads(audited.stdout)
                    truth=json.loads(subprocess.run([a.exp/'compact-vanilla-20261121/vanilla-audit',program],input='{"audit":true}\n',text=True,capture_output=True,check=True).stdout)
                    assert all(out[k]==truth[k] for k in ('rhs','writes','resumes','state_sha','schedule','runs'))
                    assert [[e for e in events if e[0]=='union'] for events in out['events']]==truth['unions']
                    row['per_run_aligned']=True
                if name=='pair' and seed==1703:
                    before=(path/'bundle-manifest.json').read_bytes()
                    again=subprocess.run(cmd,cwd=cwd,env=env,text=True,capture_output=True)
                    assert again.returncode and 'already exists' in again.stderr and (path/'bundle-manifest.json').read_bytes()==before
                    bad=folder/'unknown';failed=subprocess.run([a.native,'--compile-bundle',source,bad,'9999'],cwd=cwd,env=env,text=True,capture_output=True)
                    assert failed.returncode and not bad.exists()
                    broken=folder/'invalid.json';broken.write_bytes(b'{')
                    failed=subprocess.run([a.native,'--compile-bundle',broken,bad],cwd=cwd,env=env,text=True,capture_output=True)
                    assert failed.returncode and not bad.exists()
                    assert not list(folder.glob('.eggfuse-stage-*'))
                    row['errors_preserve_destination']=True
                results[f'{name}/{seed}']=row
                (a.out/'native.json').write_text(json.dumps(results,indent=1)+'\n')
                print(name,seed,row['rules'],row['source_rhs'],round(native_ms,1),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',choices=CASES,default=CASES)
    run(p.parse_args())

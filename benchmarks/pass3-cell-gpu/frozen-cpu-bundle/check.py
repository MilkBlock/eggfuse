"""Relocate an offline-compiled graph and validate ordinary and full-audit native entry points."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter_ns
from statistics import median
import shutil
import subprocess
import tempfile
from prepare import freeze


def cli(native,flag,folder,cwd):
    env={k:v for k,v in os.environ.items() if not k.startswith('EGGFUSE_')}
    return subprocess.run([native,flag,folder],cwd=cwd,env=env,text=True,capture_output=True)


def verify(a):
    a.out.mkdir(parents=True,exist_ok=False);report={}
    exp=a.exp
    cases={'sum-bits':(exp/'pass3-atlas-integration-20261120/sum-bits/program.json',exp/'pass3-atlas-integration-20261120/release-input-sum-bits'),
           'pair':(exp/'complete-generation-edge-v5/two/compiled/program.json',exp/'complete-generation-edge-v5/two/image')}
    for name,(program,image) in cases.items():
        start=a.out/(name+'-temp')
        freeze(program,image,a.native.resolve(),start,1703)
        dest=a.out/f'{name} moved'/ 'artifact';dest.parent.mkdir();shutil.move(start,dest)
        manifest=json.loads((dest/'bundle-manifest.json').read_bytes())
        assert all(hashlib.sha256((dest/n).read_bytes()).hexdigest()==s for n,s in manifest['files'].items())
        with tempfile.TemporaryDirectory() as cwd:
            timings=[];infer_ms=[]
            for _ in range(3):
                start_ns=perf_counter_ns();cold=cli(a.native,'--bundle',dest,cwd)
                timings.append((perf_counter_ns()-start_ns)/1e6)
                assert cold.returncode==0,(name,cold.stderr,cold.stdout[-500:])
                compact=json.loads(cold.stdout);infer_ms.append(compact['inference_ms'])
            raw=cli(a.native,'--audit-bundle',dest,cwd);assert raw.returncode==0,(name,raw.stderr)
            traced=json.loads(raw.stdout)
            ref=subprocess.run([exp/'compact-vanilla-20261121/vanilla-audit',program],input='{"audit":true}\n',cwd=cwd,text=True,capture_output=True,check=True)
            gold=json.loads(ref.stdout)
            for k in ('rhs','writes','resumes','schedule','runs','state_sha'):assert traced[k]==gold[k],(name,k)
            assert [[e for e in run if e[0]=='union'] for run in traced['events']]==gold['unions']
            winners=sorted([x[0] for x in traced['single']['committed']]+[x['ordinal'] for x in traced['multi']['tickets']])
            assert winners==list(range(1,gold['rhs_count']+1))
            assert compact['rhs']==compact['neural_rhs']==gold['rhs_count']
            execution=compact['profile_execution']
            assert execution['views']==2 and execution['sealed_before_verifier'] and execution['single_policy']==execution['multi_policy']=='learned'
            assert execution['sealed_tuples']==compact['multi_raw_tuples']
            assert compact['state_sha']==gold['state_sha'] and compact['cpu_profile']=='frozen-ports/v1' and traced['multi']['embedding_views']==2
            assert traced['multi']['paged_tuples']==compact['multi_raw_tuples'] and compact['multi_raw_tuples']>0
            if name=='sum-bits':
                assert traced['multi']['forward']['prefixes']>0 and traced['multi']['tier']['published_reads']>0
                prior=json.loads((Path(__file__).resolve().parent.parent/'tiered-port-projections/results.json').read_bytes())['sum-bits']['both']
                dig=lambda v:hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                assert traced['multi']['raw_sha256']==prior['multi'] and traced['root_recipe']['raw_hash']==prior['raw']
                assert dig(traced['root_recipe']['commits'])==prior['commits'] and dig(traced['cell_ids'])==prior['cells']
            else:
                assert len(winners)==2
            fresh={r[1]:r for r in traced['cell_ids'] if not r[4]}
            roots={r[0]:(r[1],r[3]) for r in traced['root_recipe']['fresh']}
            nested={r['allocated']:(r['parent']['ordinal'],r['template']) for r in traced['merge_child']['issued'] if r['allocated'] is not None}
            assert not (roots.keys()&nested.keys())
            for c,(ordinal,template) in {**roots,**nested}.items():assert fresh[c][0]==ordinal and fresh[c][2]==template
            v=dict(rhs=compact['rhs'],runs=compact['runs'],profile=compact['cpu_profile'],state=compact['state_sha'],
                   directly_allocated=len(roots)+len(nested),all_fresh=len(fresh),sealed=compact['multi_raw_tuples'],
                   execution=execution,cold_ms=timings,inference_ms=infer_ms,median_cold_ms=median(timings),
                   files=len(manifest['files']),compiled_plan=manifest['files']['plans.json'])
            assert 100*v['directly_allocated']>=98*v['all_fresh']
            if name=='sum-bits':
                controls={}
                for file in ('ports.bin','plans.json','request.json'):
                    target=dest/file;old=target.read_bytes()
                    try:
                        target.write_bytes(old+(b' ' if file.endswith('.json') else b'x'))
                        failed=cli(a.native,'--bundle',dest,cwd)
                        assert failed.returncode and 'bundle digest mismatch' in failed.stderr and not failed.stdout
                    finally:target.write_bytes(old)
                    controls[file]=True
                req_path=dest/'request.json';mf_path=dest/'bundle-manifest.json'
                before=req_path.read_bytes();before_mf=mf_path.read_bytes()
                try:
                    bad=json.loads(before);bad['packed_lookup']=False
                    req_path.write_text(json.dumps(bad))
                    mf=json.loads(before_mf);mf['files']['request.json']=hashlib.sha256(req_path.read_bytes()).hexdigest()
                    mf_path.write_text(json.dumps(mf))
                    failure=cli(a.native,'--bundle',dest,cwd)
                    assert failure.returncode and 'profile field mismatch: packed_lookup' in failure.stderr
                finally:
                    req_path.write_bytes(before);mf_path.write_bytes(before_mf)
                controls['incompatible_settings']=True
                v['corruptions_rejected']=controls
            report[name]=v
            print(name,v,flush=True)
    mismatched=a.out/'wrong-program-bundle'
    try:freeze(cases['pair'][0],cases['sum-bits'][1],a.native.resolve(),mismatched,1703)
    except ValueError as error:
        assert 'do not match' in str(error) and not mismatched.exists()
    else:raise AssertionError('compiler accepted an unrelated program image')
    report['pair']['foreign_image_rejected']=True
    (a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    verify(p.parse_args())
